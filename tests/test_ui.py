"""桌面界面的轻量回归测试。"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFrame,
    QLabel,
    QTextBrowser,
)

from fishing_assistant.ui import (
    FloatingStatusBar,
    InventoryCleanupTestDialog,
    InventoryCleanupWarningDialog,
    MainWindow,
    ScrollSafeComboBox,
    ScrollSafeDoubleSpinBox,
    ScrollSafeSlider,
    ScrollSafeSpinBox,
    UpdateAvailableDialog,
    WOnlyModeWarningDialog,
)
from fishing_assistant.config import AppConfig
from fishing_assistant.updates import UpdateResult


class _IgnoredWheelEvent:
    def __init__(self) -> None:
        self.ignored = False

    def ignore(self) -> None:
        self.ignored = True


class UiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_page_wheel_does_not_change_closed_inputs(self) -> None:
        controls = (
            ScrollSafeSpinBox(),
            ScrollSafeDoubleSpinBox(),
            ScrollSafeComboBox(),
            ScrollSafeSlider(),
        )
        controls[2].addItems(["第一项", "第二项"])
        for control in controls:
            event = _IgnoredWheelEvent()
            control.wheelEvent(event)  # type: ignore[arg-type]
            self.assertTrue(event.ignored, type(control).__name__)

    def test_inventory_cleanup_is_part_of_fishing_settings_navigation(self) -> None:
        titles = [title for _eyebrow, title, _subtitle in MainWindow.PAGE_META]
        self.assertEqual(
            titles,
            ["钓鱼控制台", "钓鱼设置", "识别阈值", "应用设置", "使用说明"],
        )
        self.assertNotIn("背包清理（实验性）", titles)

        owner = SimpleNamespace(_card_heading=MainWindow._card_heading)
        cleanup_card, safety_card = MainWindow._build_inventory_cleanup_cards(  # type: ignore[arg-type]
            owner
        )
        try:
            labels = "\n".join(
                label.text()
                for card in (cleanup_card, safety_card)
                for label in card.findChildren(QLabel)
            )
            self.assertIn("背包清理（实验性）", labels)
            self.assertIn("执行前安全检查", labels)
        finally:
            cleanup_card.close()
            safety_card.close()

    def test_voice_alerts_are_a_top_level_settings_card(self) -> None:
        voice_player = MagicMock()
        voice_player.available_characters.return_value = ("新海天",)
        owner = SimpleNamespace(
            _card_heading=MainWindow._card_heading,
            voice_player=voice_player,
        )
        card = MainWindow._build_voice_alert_card(owner)  # type: ignore[arg-type]
        try:
            labels = "\n".join(
                label.text() for label in card.findChildren(QLabel)
            )
            self.assertIn("语音提醒", labels)
            self.assertIn("提醒音色", labels)
            self.assertNotIn("文件名会自动对应", labels)
            self.assertEqual(owner.voice_character_combo.currentData(), "新海天")
            self.assertTrue(owner.voice_alerts_check.isChecked())
        finally:
            card.close()

    def test_disabling_voice_is_saved_and_stops_pending_playback(self) -> None:
        owner = SimpleNamespace(
            engine=MagicMock(),
            voice_player=MagicMock(),
            voice_character_combo=MagicMock(),
            _sync_voice_controls=MagicMock(),
        )
        owner.voice_character_combo.currentData.return_value = "新海天"

        MainWindow._voice_alerts_toggled(owner, False)  # type: ignore[arg-type]

        owner.engine.update_config.assert_called_once_with(
            voice_alerts_enabled=False
        )
        owner.voice_player.configure.assert_called_once_with(False, "新海天")
        owner._sync_voice_controls.assert_called_once_with()

    def test_help_page_explains_all_three_fishing_modes(self) -> None:
        owner = SimpleNamespace(_card_heading=MainWindow._card_heading)
        page = MainWindow._build_help_page(owner)  # type: ignore[arg-type]
        try:
            labels = "\n".join(label.text() for label in page.findChildren(QLabel))
            self.assertIn("使用前说明", labels)
            self.assertIn("钓鱼前务必将宠物卸下", labels)
            self.assertIn("钓鱼模式说明", labels)
            self.assertIn("模式 1 · 体力条反弹", labels)
            self.assertNotIn("模式 1 · 计时计算", labels)
            self.assertIn("14.0 秒跑鱼，会在 12.6 秒收杆", labels)
            self.assertIn("模式 2 · 定时收鱼（推荐）", labels)
            self.assertIn("模式 3 · 上钩立即收杆", labels)
        finally:
            page.close()

    def test_floating_status_bar_is_compact_topmost_and_updates(self) -> None:
        bar = FloatingStatusBar()
        try:
            self.assertLessEqual(bar.width(), 360)
            self.assertLessEqual(bar.height(), 90)
            self.assertTrue(
                bar.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
            )
            self.assertTrue(
                bar.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
            )
            bar.set_calibrated(True)
            bar.set_runtime("等待上钩", "running")
            bar.set_background_opacity(63)
            self.assertEqual(bar.calibration_label.text(), "校准 · 已完成")
            self.assertEqual(bar.runtime_label.text(), "运行 · 等待上钩")
            self.assertEqual(bar.runtime_label.property("state"), "running")
            self.assertEqual(bar.background_opacity(), 63)
            bar.show()
            self.app.processEvents()
            background = bar.grab().toImage().pixelColor(bar.width() // 2, 5)
            self.assertGreaterEqual(background.alpha(), 150)
            self.assertLessEqual(background.alpha(), 170)
        finally:
            bar.close()

    def test_floating_status_only_shows_for_minimized_background_mode(self) -> None:
        config = SimpleNamespace(
            floating_status_enabled=True,
            capture_mode="window",
        )
        owner = SimpleNamespace(
            engine=MagicMock(),
            floating_status_bar=MagicMock(),
            isMinimized=MagicMock(return_value=True),
            _sync_floating_calibration_state=MagicMock(),
        )
        owner.engine.config.return_value = config

        MainWindow._sync_floating_status_visibility(owner)  # type: ignore[arg-type]

        owner.floating_status_bar.show_at_default_position.assert_called_once()
        owner.floating_status_bar.hide.assert_not_called()

        config.capture_mode = "screen"
        MainWindow._sync_floating_status_visibility(owner)  # type: ignore[arg-type]
        owner.floating_status_bar.hide.assert_called_once()

    def test_floating_status_setting_is_saved_immediately(self) -> None:
        owner = SimpleNamespace(
            engine=MagicMock(),
            _sync_floating_status_controls=MagicMock(),
            _sync_floating_status_visibility=MagicMock(),
        )

        MainWindow._floating_status_toggled(owner, False)  # type: ignore[arg-type]

        owner.engine.update_config.assert_called_once_with(
            floating_status_enabled=False
        )
        owner._sync_floating_status_controls.assert_called_once_with()
        owner._sync_floating_status_visibility.assert_called_once_with()

    def test_floating_background_opacity_is_saved_and_previewed(self) -> None:
        owner = SimpleNamespace(
            engine=MagicMock(),
            _sync_floating_status_controls=MagicMock(),
        )

        MainWindow._floating_opacity_changed(owner, 68)  # type: ignore[arg-type]

        owner.engine.update_config.assert_called_once_with(
            floating_status_opacity=68
        )
        owner._sync_floating_status_controls.assert_called_once_with()

    def test_minimizing_background_main_window_shows_floating_status(self) -> None:
        state = {
            "config": AppConfig(
                capture_mode="window",
                target_button_offset=(1600, 860),
                floating_status_enabled=True,
                voice_alerts_enabled=False,
            )
        }
        engine = MagicMock()
        engine.config.side_effect = lambda: state["config"].copy()

        def update_config(**changes: object) -> AppConfig:
            state["config"] = state["config"].copy(**changes)
            return state["config"].copy()

        engine.update_config.side_effect = update_config
        engine.is_monitoring.return_value = False
        with patch(
            "fishing_assistant.ui.window_target.list_target_windows",
            return_value=[],
        ):
            window = MainWindow(engine)
        try:
            window.show()
            self.app.processEvents()
            window.showMinimized()
            self.app.processEvents()
            self.assertTrue(window.floating_status_bar.isVisible())
            self.assertEqual(
                window.floating_status_bar.calibration_label.text(),
                "校准 · 已完成",
            )
            window.showNormal()
            self.app.processEvents()
            self.assertFalse(window.floating_status_bar.isVisible())
        finally:
            window.close()
            self.app.processEvents()

    def test_update_dialog_is_compact_and_shows_version(self) -> None:
        result = UpdateResult(
            ok=True,
            message="发现新版本 v0.6.1",
            latest_version="v0.6.1",
            release_url="https://github.com/fanqiejiu/Mabinogi-M-Fishing-Assistant/releases/tag/v0.6.1",
            update_available=True,
            release_notes="1. 修复模式二计时。\n2. 优化更新弹窗。",
        )
        dialog = UpdateAvailableDialog(result)
        try:
            self.assertLessEqual(dialog.maximumWidth(), 430)
            self.assertGreaterEqual(dialog.minimumWidth(), 380)
            labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
            self.assertIn("发现新版本", labels)
            self.assertIn("v0.6.1", labels)
            notes = dialog.findChild(QTextBrowser, "releaseNotes")
            self.assertIsNotNone(notes)
            self.assertIn("修复模式二计时", notes.toPlainText())
        finally:
            dialog.close()

    def test_same_release_only_opens_one_popup_per_session(self) -> None:
        owner = SimpleNamespace(
            check_update_button=MagicMock(),
            update_status=MagicMock(),
            open_release_button=MagicMock(),
            _last_release_url=None,
            _notified_release_version=None,
            _append_log=MagicMock(),
            _show_update_dialog=MagicMock(),
        )
        result = UpdateResult(
            ok=True,
            message="发现新版本 v0.6.1",
            latest_version="v0.6.1",
            release_url="https://example.invalid/release",
            update_available=True,
        )

        MainWindow._show_update_result(owner, result)  # type: ignore[arg-type]
        MainWindow._show_update_result(owner, result)  # type: ignore[arg-type]

        owner._show_update_dialog.assert_called_once_with(result)
        owner.open_release_button.setEnabled.assert_called_with(True)

    def test_recovery_mode_switches_parameter_panel_and_checkbox_text(self) -> None:
        owner = SimpleNamespace(
            recovery_mode_combo=MagicMock(),
            recovery_mode_stack=MagicMock(),
            auto_recover_check=MagicMock(),
        )
        owner.recovery_mode_combo.currentData.return_value = "w_only"

        MainWindow._sync_recovery_mode_controls(owner)  # type: ignore[arg-type]

        owner.recovery_mode_stack.setCurrentIndex.assert_called_with(1)
        owner.auto_recover_check.setText.assert_called_with(
            "检测到指南针状态时仅按 W 向前恢复"
        )

        owner.recovery_mode_combo.currentData.return_value = "ws"
        MainWindow._sync_recovery_mode_controls(owner)  # type: ignore[arg-type]

        owner.recovery_mode_stack.setCurrentIndex.assert_called_with(0)
        owner.auto_recover_check.setText.assert_called_with(
            "检测到指南针状态时自动执行 W → S"
        )

    def test_pixel_fish_threshold_only_shows_in_pixel_mode(self) -> None:
        owner = SimpleNamespace(
            recognition_backend_combo=MagicMock(),
            pixel_fish_threshold_panel=MagicMock(),
            threshold_header_label=MagicMock(),
            threshold_value=MagicMock(),
            threshold_slider=MagicMock(),
            idle_min_spin=MagicMock(),
            idle_max_spin=MagicMock(),
            recognition_backend_hint=MagicMock(),
            red_metric=SimpleNamespace(
                caption_label=MagicMock(),
                value_label=MagicMock(),
            ),
            red_progress=MagicMock(),
            engine=MagicMock(),
        )
        owner.engine.config.return_value = SimpleNamespace(
            fish_red_pixel_threshold=1200
        )
        owner.recognition_backend_combo.currentData.return_value = "ok"

        MainWindow._sync_recognition_backend_controls(owner)  # type: ignore[arg-type]

        owner.pixel_fish_threshold_panel.setVisible.assert_called_with(False)

        owner.recognition_backend_combo.currentData.return_value = "pixel"
        MainWindow._sync_recognition_backend_controls(owner)  # type: ignore[arg-type]

        owner.pixel_fish_threshold_panel.setVisible.assert_called_with(True)
        owner.threshold_slider.setEnabled.assert_called_with(True)

    def test_w_only_warning_requires_acknowledgement(self) -> None:
        dialog = WOnlyModeWarningDialog()
        try:
            self.assertTrue(dialog.isModal())
            self.assertFalse(dialog.confirm_button.isEnabled())
            labels = "\n".join(
                label.text() for label in dialog.findChildren(QLabel)
            )
            self.assertIn("手动镜头", labels)
            self.assertIn("手动镜头", dialog.acknowledge_check.text())
            dialog.acknowledge_check.setChecked(True)
            self.assertTrue(dialog.confirm_button.isEnabled())
        finally:
            dialog.close()

    def test_inventory_cleanup_warning_requires_acknowledgement(self) -> None:
        dialog = InventoryCleanupWarningDialog()
        try:
            self.assertTrue(dialog.isModal())
            self.assertFalse(dialog.confirm_button.isEnabled())
            labels = "\n".join(
                label.text() for label in dialog.findChildren(QLabel)
            )
            self.assertIn("误用“大胆整理”", labels)
            dialog.acknowledge_check.setChecked(True)
            self.assertTrue(dialog.confirm_button.isEnabled())
        finally:
            dialog.close()

    def test_inventory_cleanup_debug_warning_requires_acknowledgement(self) -> None:
        dialog = InventoryCleanupTestDialog()
        try:
            self.assertTrue(dialog.isModal())
            self.assertFalse(dialog.confirm_button.isEnabled())
            dialog.acknowledge_check.setChecked(True)
            self.assertTrue(dialog.confirm_button.isEnabled())
        finally:
            dialog.close()

    def test_debug_section_contains_inventory_cleanup_as_child_option(self) -> None:
        owner = SimpleNamespace(_card_heading=MainWindow._card_heading)
        section = MainWindow._build_debug_section(owner)  # type: ignore[arg-type]
        try:
            section_labels = "\n".join(
                label.text() for label in section.findChildren(QLabel)
            )
            self.assertIn("调试", section_labels)
            option = section.findChild(QFrame, "debugOption")
            self.assertIsNotNone(option)
            option_labels = "\n".join(
                label.text() for label in option.findChildren(QLabel)
            )
            self.assertIn("背包清理测试", option_labels)
            self.assertNotIn("调试 · 背包清理测试", section_labels)
        finally:
            section.close()

    def test_cancelled_inventory_cleanup_stays_disabled(self) -> None:
        check = QCheckBox()
        check.setChecked(True)
        owner = SimpleNamespace(
            inventory_cleanup_check=check,
            engine=MagicMock(),
            _sync_inventory_cleanup_debug_controls=MagicMock(),
        )
        with patch(
            "fishing_assistant.ui.InventoryCleanupWarningDialog"
        ) as dialog_type:
            dialog_type.return_value.exec.return_value = (
                QDialog.DialogCode.Rejected
            )
            MainWindow._inventory_cleanup_toggled(  # type: ignore[arg-type]
                owner, True
            )

        self.assertFalse(check.isChecked())
        owner.engine.update_config.assert_called_once_with(
            inventory_auto_cleanup_enabled=False
        )

    def test_acknowledged_inventory_cleanup_is_saved(self) -> None:
        owner = SimpleNamespace(
            inventory_cleanup_check=MagicMock(),
            engine=MagicMock(),
            _sync_inventory_cleanup_debug_controls=MagicMock(),
        )
        with patch(
            "fishing_assistant.ui.InventoryCleanupWarningDialog"
        ) as dialog_type:
            dialog_type.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            MainWindow._inventory_cleanup_toggled(  # type: ignore[arg-type]
                owner, True
            )

        owner.engine.update_config.assert_called_once_with(
            inventory_auto_cleanup_enabled=True
        )

    def test_debug_cleanup_requires_second_confirmation(self) -> None:
        owner = SimpleNamespace(
            engine=MagicMock(),
            inventory_cleanup_test_status=MagicMock(),
            _sync_inventory_cleanup_debug_controls=MagicMock(),
        )
        owner.engine.config.return_value = SimpleNamespace(
            inventory_auto_cleanup_enabled=True
        )
        owner.engine.is_monitoring.return_value = False
        owner.engine.request_inventory_cleanup_test.return_value = True
        with patch(
            "fishing_assistant.ui.InventoryCleanupTestDialog"
        ) as dialog_type:
            dialog_type.return_value.exec.return_value = (
                QDialog.DialogCode.Accepted
            )
            MainWindow._test_inventory_cleanup(owner)  # type: ignore[arg-type]

        owner.engine.request_inventory_cleanup_test.assert_called_once_with()
        owner._sync_inventory_cleanup_debug_controls.assert_called_once_with()

    def test_cancelled_w_only_switch_returns_to_default_ws(self) -> None:
        combo = ScrollSafeComboBox()
        combo.addItem("W → S", "ws")
        combo.addItem("仅 W", "w_only")
        combo.setCurrentIndex(1)
        owner = SimpleNamespace(
            recovery_mode_combo=combo,
            engine=MagicMock(),
            _sync_recovery_mode_controls=MagicMock(),
        )
        with patch("fishing_assistant.ui.WOnlyModeWarningDialog") as dialog_type:
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Rejected
            MainWindow._recovery_mode_changed(owner)  # type: ignore[arg-type]

        self.assertEqual(combo.currentData(), "ws")
        owner.engine.update_config.assert_called_once_with(
            recovery_movement_mode="ws"
        )

    def test_acknowledged_w_only_switch_is_saved(self) -> None:
        combo = ScrollSafeComboBox()
        combo.addItem("W → S", "ws")
        combo.addItem("仅 W", "w_only")
        combo.setCurrentIndex(1)
        owner = SimpleNamespace(
            recovery_mode_combo=combo,
            engine=MagicMock(),
            _sync_recovery_mode_controls=MagicMock(),
        )
        with patch("fishing_assistant.ui.WOnlyModeWarningDialog") as dialog_type:
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            MainWindow._recovery_mode_changed(owner)  # type: ignore[arg-type]

        self.assertEqual(combo.currentData(), "w_only")
        owner.engine.update_config.assert_called_once_with(
            recovery_movement_mode="w_only"
        )


if __name__ == "__main__":
    unittest.main()
