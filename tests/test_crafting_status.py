"""制作悬浮栏、异常展示和高频状态刷新；不连接游戏。"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from fishing_assistant.config import AppConfig
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.engine import EngineEvent, EventKind
from fishing_assistant.features.crafting.model import CraftProgress
from fishing_assistant.features.fishing_history.store import FishingHistorySummary


class CraftStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.engine = MagicMock()
        self.config = AppConfig(capture_mode="screen", voice_alerts_enabled=False)
        self.engine.config.side_effect = lambda: self.config.copy()
        self.engine.update_config.side_effect = self.update_config
        self.engine.is_monitoring.return_value = False
        self.engine.is_crafting.return_value = False
        self.engine.is_paused.return_value = False
        self.engine.fishing_history_summary.return_value = FishingHistorySummary(
            0, 0, 0, 0, 0
        )
        self.engine.fishing_history_sessions.return_value = []
        self.engine._interrupt_generation = 1
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[]):
            self.window = MainWindow(self.engine)

    def update_config(self, **changes):
        self.config = self.config.copy(**changes)
        return self.config.copy()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def emit_progress(self, phase, running, message="测试制作进度"):
        progress = CraftProgress(phase, message, 0, 0, ("busy",)*5, 60, running, 1)
        self.window._consume_engine_event(EngineEvent(
            EventKind.CRAFTING, message, monitoring=running, crafting=progress, crafting_log=True))

    def test_crafting_floating_bar_ignores_fishing_capture_mode_but_respects_opt_out(self):
        self.engine.is_monitoring.return_value = True
        self.engine.is_crafting.return_value = True
        self.window.showMinimized()
        self.app.processEvents()
        self.emit_progress("inspect", True)
        bar = self.window.floating_status_bar
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.calibration_label.text(), "窗口 · 已指定")
        self.assertIn("无需 F7", bar.calibration_label.toolTip())
        self.assertIn("等待加工", bar.runtime_label.text())
        self.assertEqual(self.window.start_button.objectName(), "dangerButton")
        self.update_config(floating_status_enabled=False)
        self.window._sync_floating_status_visibility()
        self.assertFalse(bar.isVisible())

    def test_crafting_failure_is_warning_in_both_themes(self):
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            self.emit_progress("error", False, "第 2 格未确认，已停止。")
            bar = self.window.floating_status_bar
            self.assertEqual(bar.runtime_label.property("state"), "warning")
            self.assertIn("异常", bar.runtime_label.text())
            self.assertIn("第 2 格", bar.runtime_label.toolTip())
            self.assertEqual(self.window.status_chip.property("state"), "warning")
            self.assertEqual(self.window.start_button.objectName(), "primaryButton")

    def test_normal_crafting_end_restores_fishing_calibration(self):
        self.engine.is_crafting.return_value = True
        self.window._sync_floating_calibration_state()
        self.engine.is_crafting.return_value = False
        self.window._sync_floating_calibration_state()
        self.assertEqual(self.window.floating_status_bar.calibration_label.text(), "校准 · 未完成")
        self.assertNotIn("无需 F7", self.window.floating_status_bar.calibration_label.toolTip())

    def test_crafting_error_remains_visible_until_main_window_is_restored(self):
        self.engine.is_monitoring.return_value = True
        self.engine.is_crafting.return_value = True
        self.window.showMinimized()
        self.app.processEvents()
        self.emit_progress("inspect", True)
        bar = self.window.floating_status_bar
        with patch.object(bar, "show_at_default_position") as show:
            self.emit_progress("await_add", True)
            show.assert_not_called()  # 可见时不反复置顶。
        self.engine.is_monitoring.return_value = False
        self.engine.is_crafting.return_value = False
        self.emit_progress("error", False, "窗口已关闭，制作停止。")
        self.assertTrue(bar.isVisible())
        self.assertEqual(bar.runtime_label.property("state"), "warning")
        self.assertFalse(bar.pause_button.isEnabled() or bar.resume_button.isEnabled())
        self.window.showNormal()
        self.app.processEvents()
        self.assertFalse(bar.isVisible())
        self.window.showMinimized()
        self.app.processEvents()
        self.assertFalse(bar.isVisible())

    def test_changed_runtime_text_and_severity_still_update(self):
        self.window._set_runtime_state("核对队列", "running")
        self.window._set_runtime_state("确认添加", "running")
        self.assertIn("确认添加", self.window.runtime_state_chip.text())
        self.assertIn("确认添加", self.window.floating_status_bar.runtime_label.text())
        self.window._set_runtime_state("制作异常", "warning")
        self.assertEqual(self.window.runtime_state_chip.property("state"), "warning")
        self.assertEqual(self.window.floating_status_bar.runtime_label.property("state"), "warning")

    def test_unchanged_runtime_does_not_repolish_status_labels(self):
        self.window._set_runtime_state("等待上钩", "running")
        self.window._set_status("running", "● 监测中")
        labels = (self.window.runtime_state_chip, self.window.status_chip,
                  self.window.floating_status_bar.runtime_label)
        with patch.object(labels[0], "style") as first, patch.object(labels[1], "style") as second, \
             patch.object(labels[2], "style") as third:
            for _ in range(20):
                self.window._set_runtime_state("等待上钩", "running")
                self.window._set_status("running", "● 监测中")
            for style in (first, second, third):
                style.assert_not_called()


if __name__ == "__main__":
    unittest.main()
