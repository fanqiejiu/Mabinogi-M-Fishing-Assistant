"""桌面界面的轻量回归测试。"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog, QLabel, QTextBrowser

from fishing_assistant.ui import (
    MainWindow,
    ScrollSafeComboBox,
    ScrollSafeDoubleSpinBox,
    ScrollSafeSlider,
    ScrollSafeSpinBox,
    UpdateAvailableDialog,
    WOnlyModeWarningDialog,
)
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
            dialog.acknowledge_check.setChecked(True)
            self.assertTrue(dialog.confirm_button.isEnabled())
        finally:
            dialog.close()

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
