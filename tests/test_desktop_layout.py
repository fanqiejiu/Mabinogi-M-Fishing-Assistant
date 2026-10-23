"""页内分类、紧凑窗口及纯导航行为；全部使用模拟引擎。"""
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFontDatabase, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QComboBox,
    QFrame,
    QSizePolicy,
    QWidget,
)

from fishing_assistant.config import AppConfig
from fishing_assistant.desktop.design import ui_font
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.desktop.pages.sectioned import SectionedPage
from fishing_assistant.features.fishing_history.store import FishingHistorySummary
from fishing_assistant.window_target import WindowInfo
from fishing_assistant.engine import EngineEvent, EventKind


class DesktopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)

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
        for method in ("is_monitoring", "is_crafting", "is_paused"):
            getattr(self.engine, method).return_value = False
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[
            WindowInfo(123, "瑪奇 Mobile", 0, 0, 1940, 1040)
        ]):
            self.window = MainWindow(self.engine)
        self.window.setFont(ui_font())
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.crafting_page.timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_settings_and_fishing_have_distinct_sections(self):
        for index, titles in ((1, ["收鱼策略", "自动续钓", "背包清理"]),
                              (4, ["常规", "更新与关于", "诊断", "调试"])):
            page = self.window.stack.widget(index)
            self.assertIsInstance(page, SectionedPage)
            self.assertEqual([page.tabs.tabText(i) for i in range(page.tabs.count())], titles)
            self.assertEqual(page.tabs.currentIndex(), 0)
        settings = self.window.stack.widget(4)
        for key, control in (("general", self.window.voice_alerts_check),
                             ("updates", self.window.check_update_button),
                             ("diagnostics", self.window.create_bundle_button),
                             ("debug", self.window.test_inventory_cleanup_button)):
            settings.select_section(key)
            self.assertTrue(control.isVisibleTo(settings))

    def test_navigation_never_changes_configuration_or_starts_tasks(self):
        self.engine.reset_mock()
        before = self.config.copy()
        for index in range(self.window.stack.count()):
            self.window._select_page(index)
            page = self.window.stack.widget(index)
            if isinstance(page, SectionedPage):
                for tab in range(page.tabs.count()):
                    QTest.mouseClick(page.tabs, Qt.MouseButton.LeftButton, pos=page.tabs.tabRect(tab).center())
                    self.app.processEvents()
                    self.assertEqual(page.sections.currentIndex(), tab)
        self.assertEqual(self.config, before)
        self.engine.update_config.assert_not_called()
        for method in ("start", "start_crafting", "set_monitoring", "request_inventory_cleanup_test"):
            getattr(self.engine, method).assert_not_called()
        self.assertFalse(self.window.inventory_cleanup_check.isChecked())

    def test_tabs_ignore_wheel_but_allow_keyboard(self):
        self.window._select_page(4)
        page = self.window.stack.widget(4)
        for tabs in (page.tabs, self.window.crafting_hub.tabBar()):
            tabs.setCurrentIndex(0)
            event = QWheelEvent(QPointF(10, 10), QPointF(10, 10), QPoint(), QPoint(0, -120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                Qt.ScrollPhase.NoScrollPhase, False)
            QApplication.sendEvent(tabs, event)
            self.assertEqual(tabs.currentIndex(), 0)
        QTest.keyClick(page.tabs, Qt.Key.Key_Right)
        self.assertEqual(page.tabs.currentIndex(), 1)
        self.assertEqual(page.sections.currentIndex(), 1)

    def test_section_scroll_positions_are_independent_and_tabs_stay_fixed(self):
        page = SectionedPage()
        try:
            for key in ("first", "second"):
                label = QLabel(key)
                label.setMinimumHeight(1500)
                page.add_section(key, key).addWidget(label)
            page.resize(400, 300)
            page.show()
            self.app.processEvents()
            top = page.tabs.pos()
            page.verticalScrollBar().setValue(350)
            page.select_section("second")
            self.assertEqual(page.verticalScrollBar().value(), 0)
            page.verticalScrollBar().setValue(100)
            page.select_section("first")
            self.assertEqual(page.verticalScrollBar().value(), 350)
            self.assertEqual(page.tabs.pos(), top)
            with self.assertRaises(ValueError):
                page.add_section("first", "duplicate")
        finally:
            page.close()

    def test_primary_controls_fit_first_viewport_in_both_themes(self):
        page = self.window.stack.widget(0)
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            for size in ((980, 760), (900, 680)):
                self.window.resize(*size)
                page.verticalScrollBar().setValue(0)
                self.app.processEvents()
                for control in (self.window.start_button, self.window.target_mode_combo,
                                self.window.target_window_combo, self.window.refresh_windows_button):
                    position = control.mapTo(page.viewport(), QPoint())
                    self.assertTrue(page.viewport().rect().contains(position), (theme, size, control))
                    self.assertTrue(page.viewport().rect().contains(position + QPoint(control.width()-1, control.height()-1)), (theme, size, control))
                self.assertEqual(page.horizontalScrollBar().maximum(), 0)
                sizes = [x.size() for x in (self.window.runtime_state_chip, self.window.theme_button, self.window.status_chip)]
                self.assertEqual(sizes[0], sizes[1])
                self.assertEqual(sizes[1], sizes[2])

    def test_dashboard_cards_expand_with_available_window_width(self):
        page = self.window.stack.widget(0)
        canvas = page.widget()
        cards = [
            widget
            for widget in canvas.findChildren(QFrame, "card")
            if widget.parentWidget() is canvas
        ]
        self.assertEqual(len(cards), 4)
        self.window.resize(1080, 680)
        self.app.processEvents()
        narrow_widths = [card.width() for card in cards]
        self.assertEqual(self.window.width(), 1080)
        self.assertEqual(page.horizontalScrollBar().maximum(), 0)
        self.assertTrue(
            all(card.width() >= card.minimumSizeHint().width() for card in cards)
        )

        self.window.resize(1200, 760)
        self.app.processEvents()
        wide_widths = [card.width() for card in cards]

        self.assertTrue(
            all(wide > narrow for narrow, wide in zip(narrow_widths, wide_widths))
        )
        self.assertTrue(
            all(
                card.sizePolicy().horizontalPolicy()
                == QSizePolicy.Policy.Expanding
                for card in cards
            )
        )

    def test_foreground_mode_exposes_display_configuration(self):
        self.assertTrue(self.window.profile_details.content.isHidden())
        combo = self.window.target_mode_combo
        combo.setCurrentIndex(combo.findData("screen"))
        self.assertFalse(self.window.profile_details.content.isHidden())
        self.assertTrue(self.window.backend_options_panel.isHidden())
        self.assertTrue(self.window.monitor_combo.isVisibleTo(self.window.stack.widget(0)))

    def test_sidebar_keeps_application_pages_at_bottom(self):
        buttons = self.window._navigation
        self.assertEqual([b.text() for b in buttons], ["控制台", "钓鱼设置", "自动制作（测试）", "识别阈值", "设置", "使用说明", "钓鱼历史"])
        self.assertGreater(buttons[4].y() - (buttons[3].y() + buttons[3].height()), 50)

    def test_capture_input_and_recognition_use_distinct_technical_names(self):
        expected = (
            (self.window.target_mode_combo, [("window", "后台运行（推荐）"), ("screen", "前台运行")]),
            (self.window.window_backend_combo, [("ok", "Windows Graphics Capture（推荐）"), ("printwindow", "PrintWindow（兼容）")]),
            (self.window.recognition_backend_combo, [("ok", "图像模板匹配（推荐）"), ("pixel", "像素识别（旧版兼容）")]),
        )
        for combo, choices in expected:
            self.assertEqual([(combo.itemData(i), combo.itemText(i)) for i in range(combo.count())], choices)
        self.assertIsInstance(self.window.window_input_label, QLabel)
        self.assertEqual(self.window.window_input_label.text(), "窗口消息（PostMessage）")
        self.assertIn("不移动系统鼠标", self.window.window_input_label.toolTip())
        self.assertIn("不会改变输入方式", self.window.window_input_label.toolTip())
        self.assertEqual(self.window.window_backend_combo.currentData(), "ok")
        self.assertEqual(self.window.recognition_backend_combo.currentData(), "ok")

    def test_renamed_options_keep_saved_backend_choices_independent(self):
        capture = self.window.window_backend_combo
        recognition = self.window.recognition_backend_combo
        capture.setCurrentIndex(capture.findData("printwindow"))
        self.assertEqual(self.config.window_backend, "printwindow")
        self.assertEqual(self.config.recognition_backend, "ok")
        recognition.setCurrentIndex(recognition.findData("pixel"))
        self.assertEqual(self.config.window_backend, "printwindow")
        self.assertEqual(self.config.recognition_backend, "pixel")
        self.window._load_config(self.config)
        self.assertEqual(capture.currentData(), "printwindow")
        self.assertEqual(recognition.currentData(), "pixel")
        capture.setCurrentIndex(capture.findData("ok"))
        self.assertEqual(self.config.recognition_backend, "pixel")
        self.assertFalse(self.window.pixel_fish_threshold_panel.isHidden())
        self.engine.start.assert_not_called()
        self.engine.start_crafting.assert_not_called()

    def test_visible_copy_and_help_do_not_use_ambiguous_backend_labels(self):
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            self.app.processEvents()
            texts = []
            for widget in self.window.findChildren(QWidget):
                texts.append(widget.toolTip())
                if isinstance(widget, QLabel):
                    texts.append(widget.text())
                if isinstance(widget, QComboBox):
                    texts.extend(widget.itemText(i) for i in range(widget.count()))
                    texts.extend(str(widget.itemData(i, Qt.ItemDataRole.ToolTipRole) or "") for i in range(widget.count()))
            for obsolete in ("OK 后台", "OK 引擎", "后台引擎", "兼容引擎", "指定窗口后台模式", "屏幕坐标模式"):
                self.assertNotIn(obsolete, "\n".join(texts))
        help_text = "\n".join(label.text() for label in self.window.stack.widget(5).findChildren(QLabel))
        for term in ("Windows Graphics Capture", "PrintWindow", "PostMessage", "FeatureSet", "不会自动切换"):
            self.assertIn(term, help_text)

    def test_live_metrics_keep_algorithm_name_without_framework_brand(self):
        self.engine.is_monitoring.return_value = True
        self.window._consume_engine_event(EngineEvent(
            EventKind.METRIC, "识别完成", monitoring=True,
            recognition_source="ok_feature", recognition_confidence=0.75,
        ))
        self.assertEqual(self.window.red_metric.caption_label.text(), "图标匹配相似度")
        self.assertEqual(self.window.red_metric.value_label.text(), "75.0%")


if __name__ == "__main__":
    unittest.main()
