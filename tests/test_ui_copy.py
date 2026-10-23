"""操作页精简文案回归；信息按需显示，安全警告和错误不能隐藏。"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from fishing_assistant.config import AppConfig
from fishing_assistant.desktop.forms import FormHelpersMixin
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.desktop.widgets import DetailsPanel
from fishing_assistant.features.crafting.model import CraftProgress
from fishing_assistant.engine import EngineEvent, EventKind
from fishing_assistant.features.fishing_history.store import FishingHistorySummary
from fishing_assistant.window_target import WindowInfo


class CompactCopyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.engine = MagicMock()
        self.config = AppConfig(voice_alerts_enabled=False)
        self.engine.config.side_effect = lambda: self.config.copy()
        def update(**changes):
            self.config = self.config.copy(**changes)
            return self.config.copy()
        self.engine.update_config.side_effect = update
        self.engine.fishing_history_summary.return_value = FishingHistorySummary(
            0, 0, 0, 0, 0
        )
        self.engine.fishing_history_sessions.return_value = []
        self.engine.is_monitoring.return_value = False
        self.engine.is_crafting.return_value = False
        self.engine.is_paused.return_value = False
        target = WindowInfo(123, "瑪奇 Mobile", 0, 0, 1940, 1040)
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[target]):
            self.window = MainWindow(self.engine)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.crafting_page.timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_field_help_is_available_without_a_second_text_row(self):
        field = FormHelpersMixin._form_label("轮询间隔", "越短反馈越快")
        try:
            self.assertEqual([label.text() for label in field.findChildren(QLabel)], ["轮询间隔"])
            self.assertEqual(field.toolTip(), "越短反馈越快")
            self.assertEqual(field.accessibleDescription(), "越短反馈越快")
            self.assertEqual(field.findChild(QLabel).toolTip(), "越短反馈越快")
        finally:
            field.close()

    def test_card_description_is_not_repeated_below_heading(self):
        parent = QWidget()
        heading = FormHelpersMixin._card_heading("运行状态", "补充说明")
        parent.setLayout(heading)
        self.assertEqual(heading.count(), 1)
        self.assertEqual(heading.itemAt(0).widget().toolTip(), "补充说明")
        parent.close()

    def test_supplementary_steps_can_be_expanded_using_keyboard(self):
        self.window._select_page(1)
        self.window.stack.widget(1).select_section("cleanup")
        details = self.window.stack.widget(1).findChild(DetailsPanel)
        self.assertIsNotNone(details)
        self.assertTrue(details.content.isHidden())
        self.assertEqual(details.toggle.arrowType(), Qt.ArrowType.RightArrow)
        QTest.keyClick(details.toggle, Qt.Key.Key_Space)
        self.assertFalse(details.content.isHidden())
        self.assertEqual(details.toggle.arrowType(), Qt.ArrowType.DownArrow)
        self.assertIn("连续确认 3 帧", " ".join(x.text() for x in details.content.findChildren(QLabel)))
        QTest.keyClick(details.toggle, Qt.Key.Key_Space)
        self.assertTrue(details.content.isHidden())
        self.engine.request_inventory_cleanup_test.assert_not_called()
        self.engine.start_crafting.assert_not_called()

    def test_cleanup_risks_are_visible_and_readable_in_both_themes(self):
        def luminance(color):
            values = [x/12.92 if x <= .04045 else ((x+.055)/1.055)**2.4 for x in color.getRgbF()[:3]]
            return sum(x*w for x,w in zip(values,(.2126,.7152,.0722)))
        for theme in ("day", "night", "day"):
            self.window._apply_theme(theme)
            for index in (1,4):
                self.window._select_page(index)
                self.app.processEvents()
                page = self.window.stack.widget(index)
                page.select_section("cleanup" if index == 1 else "debug")
                self.app.processEvents()
                risk = next(x for x in page.findChildren(QLabel,"safetyWarning") if "大胆整理" in x.text())
                self.assertTrue(risk.isVisibleTo(page))
                self.assertTrue(all(details.content.isHidden() for details in page.findChildren(DetailsPanel)))
                foreground = luminance(risk.palette().color(QPalette.ColorRole.WindowText))
                background = luminance(risk.parentWidget().palette().color(QPalette.ColorRole.Window))
                self.assertGreaterEqual((max(foreground,background)+.05)/(min(foreground,background)+.05),4.5)

    def test_mode_calculation_is_in_help_and_runtime_record_is_kept(self):
        texts = "\n".join(x.text() for x in self.window.stack.widget(5).findChildren(QLabel))
        self.assertIn("T × 10%",texts)
        self.assertIn("14.0 秒跑鱼，会在 12.6 秒收杆",texts)
        self.assertIn("钓鱼前务必将宠物卸下",texts)
        self.engine.update_config(learned_escape_seconds=14.0)
        self.window._sync_learned_escape_status()
        self.assertIn("12.6",self.window.learned_escape_label.text())
        self.assertIn("钓鱼计时", "\n".join(x.text() for x in self.window.stack.widget(1).findChildren(QLabel)))

    def test_available_backend_controls_do_not_look_disabled(self):
        self.window._select_page(0)
        for theme,disabled_color in (("day","#8a9aaf"),("night","#5e728a"),("day","#8a9aaf")):
            self.window._apply_theme(theme)
            self.app.processEvents()
            for combo in (self.window.target_window_combo,self.window.window_backend_combo):
                self.assertTrue(combo.isEnabled())
                self.assertNotEqual(combo.palette().color(QPalette.ColorRole.Text).name(),disabled_color)
        self.window.target_mode_combo.setCurrentIndex(self.window.target_mode_combo.findData("screen"))
        self.assertTrue(self.window.backend_options_panel.isHidden())
        self.window.target_mode_combo.setCurrentIndex(self.window.target_mode_combo.findData("window"))
        self.assertFalse(self.window.backend_options_panel.isHidden())
        self.assertTrue(self.window.target_window_combo.isEnabled())

    def test_delay_limit_warning_only_appears_when_relevant(self):
        combo = self.window.catch_strategy_combo
        combo.setCurrentIndex(combo.findData("fixed_delay"))
        self.assertTrue(self.window.fixed_delay_effective_hint.isHidden())
        self.window.fallback_delay_spin.setValue(12.5)
        self.assertFalse(self.window.fixed_delay_effective_hint.isHidden())
        self.assertIn("10.5 秒", self.window.fixed_delay_effective_hint.text())
        self.window.fallback_delay_spin.setValue(5.3)
        self.assertTrue(self.window.fixed_delay_effective_hint.isHidden())

    def test_w_only_camera_warning_remains_in_configured_mode(self):
        self.engine.update_config(recovery_movement_mode="w_only")
        self.window._load_config(self.config)
        self.window._select_page(1)
        self.window.stack.widget(1).select_section("recovery")
        self.app.processEvents()
        warnings = self.window.recovery_mode_stack.currentWidget().findChildren(QLabel,"safetyWarning")
        self.assertTrue(any("手动镜头" in x.text() and x.isVisibleTo(self.window.stack.widget(1)) for x in warnings))

    def test_idle_crafting_does_not_show_repetitive_rule_paragraphs(self):
        page = self.window.crafting_page
        self.assertTrue(page.availability.isHidden())
        self.assertTrue(page.detail.isHidden())
        self.assertTrue(page.estimate.isHidden())
        self.assertIn("不是产物件数", page.count.toolTip())
        self.assertLess(len(page.rule.text()), 50)
        self.assertLess(len(page.timing.text()), 40)

    def test_crafting_error_keeps_entire_message_visible_and_logged(self):
        page = self.window.crafting_page
        message = "未能确认第 5 格队列：窗口尺寸发生改变，请检查目标画面后重试。"
        self.window._select_page(2)
        page.update_progress(CraftProgress("error",message,0,0,("unknown",)*5,0,False),log=True)
        self.assertFalse(page.detail.isHidden())
        self.assertEqual(page.detail.text(),message)
        self.assertIn(message,page.log.toPlainText())

    def test_technical_details_are_not_permanent_operation_page_labels(self):
        for index in (0,1,2,3,4):
            self.window._select_page(index)
            self.app.processEvents()
            page = self.window.stack.widget(index)
            labels = "\n".join(x.text() for x in page.findChildren(QLabel) if x.isVisibleTo(page))
            for removed in ("WM_ACTIVATE", "FeatureSet", "后续新增人物文件夹", "后续调试项目", "max(1.0 秒"):
                self.assertNotIn(removed,labels)
        self.engine.start.assert_not_called()
        self.engine.start_crafting.assert_not_called()
        self.engine.set_monitoring.assert_not_called()

    def test_stopping_is_not_described_as_resumable_pause(self):
        self.engine.is_monitoring.return_value = True
        self.window._consume_engine_event(EngineEvent(EventKind.STATE,"开始监测",monitoring=True))
        self.assertEqual(self.window.start_button.text(),"停止监测")
        self.engine.is_paused.return_value = True
        self.window._consume_engine_event(EngineEvent(EventKind.PAUSE,"已暂停当前任务",monitoring=True))
        self.assertEqual(self.window.runtime_title.text(),"已暂停")
        self.engine.is_paused.return_value = False
        self.engine.is_monitoring.return_value = False
        self.window._consume_engine_event(EngineEvent(EventKind.STATE,"F8 已停止当前任务"))
        self.assertEqual(self.window.runtime_title.text(),"已停止")
        self.assertEqual(self.window.runtime_detail.text(),"F8 已停止当前任务")
        self.assertIn("已停止",self.window.runtime_state_chip.text())
        self.assertEqual(self.window.start_button.text(),"开始监测")
        self.window._consume_engine_event(EngineEvent(EventKind.ERROR,"窗口不可用，请重新选择。"))
        self.assertEqual(self.window.runtime_title.text(),"已停止")
        self.assertIn("识别已停止",self.window.status_chip.text())
        self.assertEqual(self.window.runtime_detail.text(),"窗口不可用，请重新选择。")


if __name__ == "__main__":
    unittest.main()
