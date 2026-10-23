"""可配置停止键：持久化、实时切换和任务取消；不安装系统监听或操作游戏。"""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pynput import keyboard
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication
from fishing_assistant.config import (
    AppConfig, STOP_HOTKEY_LABELS, load_config, save_config,
)
from fishing_assistant.engine import FishingEngine, EventKind
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.desktop.widgets import ScrollSafeComboBox


class StopHotkeyConfigTests(unittest.TestCase):
    def test_old_config_keeps_esc_and_explicit_selection_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch("fishing_assistant.config.CONFIG_PATH", path):
                path.write_text(json.dumps({"schema_version": 22, "recognition_backend": "pixel"}), encoding="utf-8")
                config = load_config()
                self.assertEqual(config.stop_hotkey, "esc")
                self.assertEqual(config.recognition_backend, "pixel")
                for key in STOP_HOTKEY_LABELS:
                    save_config(config.copy(stop_hotkey=key))
                    self.assertEqual(load_config().stop_hotkey, key)
                    self.assertEqual(load_config().recognition_backend, "pixel")

    def test_invalid_and_reserved_bindings_fall_back_without_losing_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            with patch("fishing_assistant.config.CONFIG_PATH", path):
                for invalid in (None, [], {}, False, "", "f7", "f8", "f9", "w", "ctrl+q"):
                    path.write_text(json.dumps({"schema_version": 22, "stop_hotkey": invalid,
                        "voice_alerts_enabled": False}), encoding="utf-8")
                    self.assertEqual(load_config().stop_hotkey, "esc")
                    self.assertFalse(load_config().voice_alerts_enabled)


class StopHotkeyEngineTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        with patch("fishing_assistant.engine.load_config", return_value=AppConfig()):
            self.engine = FishingEngine(self.events.append)
        self.engine._enabled.set()

    def press(self, key):
        self.engine._on_key_press(key)

    def release(self, key):
        self.engine._on_key_release(key)

    def test_each_selected_key_stops_once_and_invalidates_old_operations(self):
        for name in STOP_HOTKEY_LABELS:
            if name == "none":
                continue
            with self.subTest(key=name):
                self.engine._config = AppConfig(stop_hotkey=name)
                self.engine._enabled.set()
                self.events.clear()
                key = getattr(keyboard.Key, name)
                generation = self.engine._interrupt_generation
                self.press(key)
                self.press(key)
                self.assertFalse(self.engine.is_monitoring())
                self.assertFalse(self.engine._operation_active(generation))
                self.assertEqual(sum(event.kind == EventKind.WARNING for event in self.events), 1)
                self.release(key)

    def test_other_game_esc_is_ignored_after_rebinding_or_disabling(self):
        for choice in ("f10", "none"):
            self.engine._config = AppConfig(stop_hotkey=choice)
            for _ in range(5):
                self.press(keyboard.Key.esc)
                self.release(keyboard.Key.esc)
                self.press(keyboard.KeyCode.from_char("w"))
                self.press(None)
            self.assertTrue(self.engine.is_monitoring())
            self.assertEqual(self.events, [])
        self.press(keyboard.Key.f10)
        self.assertTrue(self.engine.is_monitoring())
        self.release(keyboard.Key.f10)
        self.engine._config = AppConfig(stop_hotkey="f10")
        self.press(keyboard.Key.f10)
        self.assertFalse(self.engine.is_monitoring())

    def test_changes_apply_live_without_restarting_or_reusing_held_key(self):
        self.engine._config = AppConfig(stop_hotkey="f10")
        self.press(keyboard.Key.f11)
        with patch("fishing_assistant.engine.save_config"):
            self.engine.update_config(stop_hotkey="f11")
        self.press(keyboard.Key.f11)
        self.assertTrue(self.engine.is_monitoring())
        self.press(keyboard.Key.f10)
        self.assertTrue(self.engine.is_monitoring())
        self.release(keyboard.Key.f11)
        self.press(keyboard.Key.f11)
        self.assertFalse(self.engine.is_monitoring())

    def test_internal_esc_guard_does_not_disable_different_stop_key(self):
        self.engine._ignore_esc_until = float("inf")
        self.press(keyboard.Key.esc)
        self.assertTrue(self.engine.is_monitoring())
        self.release(keyboard.Key.esc)
        self.engine._config = AppConfig(stop_hotkey="f10")
        self.press(keyboard.Key.f10)
        self.assertFalse(self.engine.is_monitoring())

    def test_disabled_stop_key_keeps_f8_and_calibration_diagnostics(self):
        self.engine._config = AppConfig(stop_hotkey="none")
        for key, method in ((keyboard.Key.f7, "calibrate_from_cursor"),
                            (keyboard.Key.f9, "request_debug_capture")):
            with patch.object(self.engine, method) as action:
                self.press(key)
                self.press(key)
                action.assert_called_once()
            self.release(key)
        self.press(keyboard.Key.f8)
        self.assertFalse(self.engine.is_monitoring())

    def test_custom_stop_clears_debug_and_crafting_requests(self):
        self.engine._config = AppConfig(stop_hotkey="pause")
        self.engine._cleanup_test_requested.set()
        session = MagicMock()
        self.engine._craft_request = (session, MagicMock())
        self.press(keyboard.Key.pause)
        self.assertFalse(self.engine._cleanup_test_requested.is_set())
        self.assertIsNone(self.engine._craft_request)
        session.stop.assert_called_once()
        self.events.clear()
        self.release(keyboard.Key.pause)
        self.press(keyboard.Key.pause)
        self.assertEqual(self.events, [])


class StopHotkeyUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_choices_save_update_hints_and_ignore_scroll_in_both_themes(self):
        engine = MagicMock()
        config = [AppConfig(stop_hotkey="f11", voice_alerts_enabled=False)]
        engine.config.side_effect = lambda: config[0].copy()
        def update(**changes):
            config[0] = config[0].copy(**changes)
            return config[0].copy()
        engine.update_config.side_effect = update
        for method in ("is_monitoring", "is_crafting", "is_paused"):
            getattr(engine, method).return_value = False
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[]):
            window = MainWindow(engine)
        try:
            self.assertEqual(window.stop_hotkey_combo.currentData(), "f11")
            engine.update_config.assert_not_called()
            window.resize(920, 680)
            window.show()
            window._select_page(4)
            window.stack.widget(4).select_section("general")
            for theme in ("day", "night"):
                window._apply_theme(theme)
                self.app.processEvents()
                combo = window.stop_hotkey_combo
                self.assertIsInstance(combo, ScrollSafeComboBox)
                self.assertTrue(combo.isVisibleTo(window))
                for value, text in (("none", "F8"), ("f10", "F8 / F10"), ("esc", "F8 / Esc")):
                    combo.setCurrentIndex(combo.findData(value))
                    self.assertEqual(config[0].stop_hotkey, value)
                    self.assertEqual(window.crafting_page.stop.text(), f"停止（{text}）")
                    self.assertEqual(window.stop_hotkey_help_key.text(), STOP_HOTKEY_LABELS[value])
                    self.assertTrue(window.stop_hotkey_help_detail.text())
                    event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, -120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
                    engine.update_config.reset_mock()
                    QApplication.sendEvent(combo, event)
                    self.assertEqual(combo.currentData(), value)
                    engine.update_config.assert_not_called()
                self.assertFalse(config[0].inventory_auto_cleanup_enabled)
                self.assertEqual(window.stack.widget(4).current_scroll().horizontalScrollBar().maximum(), 0)
            for method in ("start", "start_crafting", "set_monitoring", "request_inventory_cleanup_test"):
                getattr(engine, method).assert_not_called()
        finally:
            window.crafting_page.timer.stop()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
