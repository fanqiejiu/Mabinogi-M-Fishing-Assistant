"""首次显示主题与窗口发现回归；模拟引擎，绝不启动真实任务。"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QWidget

from fishing_assistant.config import AppConfig
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.features.fishing_history.store import FishingHistorySummary
from fishing_assistant.window_target import WindowInfo


class StartupPresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    def build(self, config=None, windows=(), discovery_error=None):
        self.config = config or AppConfig(voice_alerts_enabled=False)
        self.engine = MagicMock()
        self.engine.config.side_effect = lambda: self.config.copy()
        def update(**changes):
            self.config = self.config.copy(**changes)
            return self.config.copy()
        self.engine.update_config.side_effect = update
        self.engine.is_monitoring.return_value = False
        self.engine.is_crafting.return_value = False
        self.engine.is_paused.return_value = False
        self.engine.fishing_history_summary.return_value = FishingHistorySummary(
            0, 0, 0, 0, 0
        )
        self.engine.fishing_history_sessions.return_value = []
        with patch("fishing_assistant.window_target.list_target_windows", return_value=list(windows),
                   side_effect=discovery_error):
            window = MainWindow(self.engine)
        self.addCleanup(self.dispose, window)
        window.show()
        self.app.processEvents()
        return window

    def dispose(self, window):
        window.crafting_page.timer.stop()
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_first_frame_and_hidden_pages_match_theme_without_toggle(self):
        for theme in ("day", "night"):
            with self.subTest(theme=theme):
                window = self.build(AppConfig(ui_theme=theme, voice_alerts_enabled=False))
                widgets = window.findChildren(QWidget)
                roles = (QPalette.Window, QPalette.WindowText, QPalette.Base,
                         QPalette.Text, QPalette.Button, QPalette.ButtonText)
                def palettes():
                    return [tuple(w.palette().color(group, role).name()
                                  for group in (QPalette.Active, QPalette.Disabled)
                                  for role in roles) for w in widgets]
                before = palettes()
                # 第一次显示不能依赖用户切换，也检查未打开页面的缓存。
                for canvas in window.findChildren(QWidget, "pageCanvas"):
                    self.assertEqual(canvas.palette().color(QPalette.Window).name(),
                                     "#f4f7fb" if theme == "day" else "#09111f")
                window._apply_theme("night" if theme == "day" else "day")
                self.app.processEvents()
                window._apply_theme(theme)
                self.app.processEvents()
                self.assertEqual(before, palettes())
                self.assertEqual(self.config.ui_theme, theme)
                self.engine.start.assert_not_called()
                self.engine.start_crafting.assert_not_called()

    def test_minimized_game_is_found_by_both_pages_and_restore_refreshes(self):
        target = WindowInfo(123, "瑪奇 Mobile", 0, 0, 1940, 1040, True)
        window = self.build(windows=[target])
        self.assertEqual(window.target_window_combo.currentData(), target)
        self.assertEqual(window.crafting_page.target.currentData(), 123)
        self.assertIn("已最小化", window.target_window_combo.currentText())
        self.assertIn("已最小化", window.target_mode_status.text())
        self.assertIn("已最小化", window.crafting_page.availability.text())
        self.assertFalse(window.crafting_page.start.isEnabled())
        self.assertEqual(self.config.selected_resolution, AppConfig().selected_resolution)
        window.crafting_page.start_task()
        self.engine.start_crafting.assert_not_called()
        restored = WindowInfo(123, target.title, 20, 30, 2560, 1600)
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[restored]):
            window._refresh_target_windows()
            window.crafting_page.refresh_windows()
        self.assertEqual(window.target_window_combo.currentData(), restored)
        self.assertNotIn("已最小化", window.target_mode_status.text())
        self.assertTrue(window.crafting_page.start.isEnabled())
        self.assertIn("2560", self.config.selected_resolution)

    def test_unrelated_windows_are_not_automatically_selected(self):
        window = self.build(windows=[WindowInfo(42, "浏览器", 0, 0, 1024, 768)])
        self.assertIsNone(window.target_window_combo.currentData())
        self.assertIsNone(window.crafting_page.target.currentData())
        self.assertEqual(self.config.target_window_handle, 0)

    def test_saved_manual_selection_survives_refresh_and_busy_refresh_is_ignored(self):
        manual = WindowInfo(42, "用户选择的游戏", 0, 0, 1280, 800)
        game = WindowInfo(123, "瑪奇 Mobile", 0, 0, 1940, 1040)
        window = self.build(AppConfig(target_window_handle=42, target_window_title=manual.title,
                                      voice_alerts_enabled=False), [manual, game])
        self.assertEqual(window.target_window_combo.currentData(), manual)
        self.assertEqual(window.crafting_page.target.currentData(), 42)
        self.engine.is_monitoring.return_value = True
        with patch("fishing_assistant.window_target.list_target_windows") as enumerate_windows:
            window._refresh_target_windows()
            window.crafting_page.refresh_windows()
        enumerate_windows.assert_not_called()
        self.assertEqual(self.config.target_window_handle, 42)

    def test_discovery_error_is_visible_and_does_not_crash_startup(self):
        window = self.build(discovery_error=OSError("测试枚举失败"))
        self.assertIn("测试枚举失败", window.target_mode_status.text())
        self.assertIn("测试枚举失败", window.crafting_page.availability.text())
        with patch("fishing_assistant.window_target.list_target_windows", side_effect=OSError("测试枚举失败")):
            window._refresh_target_windows()
            window.crafting_page.refresh_windows()
        self.assertIn("测试枚举失败", window.target_mode_status.text())
        self.assertIn("测试枚举失败", window.crafting_page.availability.text())
        self.assertFalse(window.crafting_page.start.isEnabled())
