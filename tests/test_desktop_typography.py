"""桌面字号、文本裁切和独立进程 DPI 回归；绝不连接真实游戏。"""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if "--dpi-probe" in sys.argv:
    os.environ["QT_SCALE_FACTOR"] = sys.argv[sys.argv.index("--dpi-probe") + 1]

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (
    QApplication, QLabel, QComboBox, QStyle, QStyleOptionComboBox,
    QStyleOptionButton, QScrollArea,
)
from fishing_assistant.config import AppConfig
from fishing_assistant.desktop.design import ui_font, FONT_FAMILIES
from fishing_assistant.desktop.dialogs import (
    WOnlyModeWarningDialog, InventoryCleanupWarningDialog, InventoryCleanupTestDialog,
)
from fishing_assistant.desktop.floating_status import FloatingStatusBar
from fishing_assistant.desktop.main_window import MainWindow
from fishing_assistant.desktop.pages.sectioned import SectionedPage
from fishing_assistant.features.fishing_history.store import FishingHistorySummary
from fishing_assistant.window_target import WindowInfo


class TypographyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        for name in ("segoeui.ttf", "segoeuib.ttf", "msyh.ttc", "msyhbd.ttc"):
            QFontDatabase.addApplicationFont("C:/Windows/Fonts/" + name)

    def setUp(self):
        self.engine = MagicMock()
        self.engine.config.return_value = AppConfig(voice_alerts_enabled=False)
        self.engine.fishing_history_summary.return_value = FishingHistorySummary(
            0, 0, 0, 0, 0
        )
        self.engine.fishing_history_sessions.return_value = []
        for name in ("is_monitoring", "is_crafting", "is_paused"):
            getattr(self.engine, name).return_value = False
        with patch("fishing_assistant.window_target.list_target_windows", return_value=[
            WindowInfo(123, "瑪奇 Mobile", 0, 0, 1940, 1040)
        ]):
            self.window = MainWindow(self.engine)
        self.window.setFont(ui_font())
        self.window.resize(900, 680)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        for name in ("start", "start_crafting", "set_monitoring", "request_inventory_cleanup_test"):
            getattr(self.engine, name).assert_not_called()
        self.window.crafting_page.timer.stop()
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_semantic_sizes_and_chinese_font_fallback_match_both_themes(self):
        self.assertEqual(ui_font().families(), list(FONT_FAMILIES))
        self.assertEqual(ui_font().pixelSize(), 14)
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            for role, size in (("pageTitle", 24), ("cardTitle", 16), ("formLabel", 14),
                               ("helper", 13), ("safetyWarning", 14), ("shortcutKey", 18)):
                labels = self.window.findChildren(QLabel, role)
                self.assertTrue(labels, role)
                for label in labels:
                    label.ensurePolished()
                    self.assertEqual(label.font().pixelSize(), size, (theme, role, label.text()))
            self.assertEqual(self.window.target_mode_combo.font().pixelSize(), 14)

    def test_pages_do_not_clip_selected_options_or_scroll_horizontally(self):
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            for index in range(self.window.stack.count()):
                self.window._select_page(index)
                page = self.window.stack.widget(index)
                tabs = page.tabs if isinstance(page, SectionedPage) else (
                    self.window.crafting_hub if index == 2 else None)
                for variant in range(tabs.count() if tabs else 1):
                    if tabs:
                        tabs.setCurrentIndex(variant)
                    self.app.processEvents()
                    for area in ([page] if isinstance(page, QScrollArea) else page.findChildren(QScrollArea)):
                        if area.isVisibleTo(page):
                            self.assertEqual(area.horizontalScrollBar().maximum(), 0, (theme, index, variant))
                    for combo in page.findChildren(QComboBox):
                        if not combo.isVisibleTo(page):
                            continue
                        option = QStyleOptionComboBox()
                        combo.initStyleOption(option)
                        rect = combo.style().subControlRect(QStyle.ComplexControl.CC_ComboBox,
                            option, QStyle.SubControl.SC_ComboBoxEditField, combo)
                        self.assertGreaterEqual(rect.width(), combo.fontMetrics().horizontalAdvance(combo.currentText()),
                            (theme, index, variant, combo.currentText()))
                        self.assertGreaterEqual(rect.height(), combo.fontMetrics().height())

    def test_warning_dialogs_keep_readable_text_and_explicit_consent(self):
        for theme in ("day", "night"):
            self.window._apply_theme(theme)
            for cls in (WOnlyModeWarningDialog, InventoryCleanupWarningDialog, InventoryCleanupTestDialog):
                dialog = cls(self.window)
                try:
                    dialog.show()
                    dialog.adjustSize()
                    self.app.processEvents()
                    check = dialog.acknowledge_check
                    option = QStyleOptionButton()
                    check.initStyleOption(option)
                    rect = check.style().subElementRect(QStyle.SubElement.SE_CheckBoxContents, option, check)
                    self.assertGreaterEqual(rect.width(), check.fontMetrics().horizontalAdvance(check.text()), cls.__name__)
                    self.assertGreaterEqual(rect.height(), check.fontMetrics().height())
                    for label in dialog.findChildren(QLabel):
                        if label.wordWrap():
                            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()), label.text())
                        else:
                            self.assertGreaterEqual(label.width(), label.fontMetrics().horizontalAdvance(label.text()), label.text())
                    self.assertFalse(check.isChecked())
                    self.assertFalse(dialog.confirm_button.isEnabled())
                    check.setChecked(True)
                    self.assertTrue(dialog.confirm_button.isEnabled())
                    check.setChecked(False)
                    self.assertFalse(dialog.confirm_button.isEnabled())
                finally:
                    dialog.close()
                    dialog.deleteLater()

    def test_status_chips_and_floating_controls_keep_text_inside(self):
        floating = FloatingStatusBar()
        try:
            for theme in ("day", "night"):
                self.window._apply_theme(theme)
                floating.set_theme(theme)
                floating.set_task_controls(True, False)
                floating.set_runtime("等待上钩")
                floating.show()
                self.app.processEvents()
                chips = (self.window.runtime_state_chip, self.window.theme_button, self.window.status_chip)
                self.assertEqual(chips[0].size(), chips[1].size())
                self.assertEqual(chips[1].size(), chips[2].size())
                for label in (chips[0], chips[2], *floating.findChildren(QLabel)):
                    self.assertGreaterEqual(label.contentsRect().width(), label.fontMetrics().horizontalAdvance(label.text()), label.text())
                    self.assertGreaterEqual(label.contentsRect().height(), label.fontMetrics().height(), label.text())
                for button in (floating.pause_button, floating.resume_button):
                    self.assertLess(button.width(), floating.runtime_label.width())
                    self.assertGreaterEqual(button.height(), button.fontMetrics().height() + 4)
        finally:
            floating.close()
            floating.deleteLater()

    def test_requested_dpi_scales_rendering_not_logical_text_size(self):
        expected = float(os.environ.get("QT_SCALE_FACTOR", "1"))
        self.assertAlmostEqual(self.window.devicePixelRatioF(), expected, places=2)
        snapshot = self.window.grab()
        self.assertAlmostEqual(snapshot.width(), self.window.width() * expected, delta=1)
        self.assertEqual(self.window.target_mode_combo.font().pixelSize(), 14)


class DpiProcessTests(unittest.TestCase):
    def test_100_125_150_200_percent_in_separate_qt_processes(self):
        # Qt 在创建 QApplication 时读取缩放，不能在同一个进程里伪造切换。
        for scale in ("1", "1.25", "1.5", "2"):
            with self.subTest(scale=scale):
                env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8",
                           QT_AUTO_SCREEN_SCALE_FACTOR="0", QT_SCREEN_SCALE_FACTORS="")
                result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--dpi-probe", scale],
                    cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=45)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    if "--dpi-probe" in sys.argv:
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(TypographyTests))
        raise SystemExit(not result.wasSuccessful())
    unittest.main()
