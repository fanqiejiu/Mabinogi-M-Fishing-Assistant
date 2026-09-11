"""钓鱼策略和恢复配置。"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QDialog

from ... import window_target
from ...engine import EventKind, FishingEngine


class FishingConfigurationMixin:
    def _catch_strategy_changed(self) -> None:
        self.engine.update_config(catch_strategy=str(self.catch_strategy_combo.currentData()))
        self._sync_catch_strategy_controls()

    def _recovery_mode_changed(self) -> None:
        mode = str(self.recovery_mode_combo.currentData())
        if mode == "w_only":
            from .. import WOnlyModeWarningDialog

            dialog = WOnlyModeWarningDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                blocker = QSignalBlocker(self.recovery_mode_combo)
                ws_index = self.recovery_mode_combo.findData("ws")
                self.recovery_mode_combo.setCurrentIndex(max(0, ws_index))
                del blocker
                self.engine.update_config(recovery_movement_mode="ws")
                self._sync_recovery_mode_controls()
                return
        self.engine.update_config(recovery_movement_mode=mode)
        self._sync_recovery_mode_controls()

    def _sync_recovery_mode_controls(self) -> None:
        mode = str(self.recovery_mode_combo.currentData())
        self.recovery_mode_stack.setCurrentIndex(1 if mode == "w_only" else 0)
        self.auto_recover_check.setText(
            "检测到指南针状态时仅按 W 向前恢复"
            if mode == "w_only"
            else "检测到指南针状态时自动执行 W → S"
        )

    def _inventory_cleanup_toggled(self, checked: bool) -> None:
        if checked:
            from .. import InventoryCleanupWarningDialog

            dialog = InventoryCleanupWarningDialog(self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                blocker = QSignalBlocker(self.inventory_cleanup_check)
                self.inventory_cleanup_check.setChecked(False)
                del blocker
                self.engine.update_config(
                    inventory_auto_cleanup_enabled=False
                )
                self._sync_inventory_cleanup_debug_controls()
                return
        self.engine.update_config(inventory_auto_cleanup_enabled=checked)
        self._sync_inventory_cleanup_debug_controls()

    def _sync_inventory_cleanup_debug_controls(self) -> None:
        config = self.engine.config()
        calibrated = (
            config.target_button_offset is not None
            if config.capture_mode == "window"
            else config.button_center is not None
        )
        monitoring = self.engine.is_monitoring()
        self.test_inventory_cleanup_button.setEnabled(
            calibrated and not monitoring
        )
        if not calibrated:
            message = "请先回到控制台完成 F7 校准。"
        elif monitoring:
            message = "当前监测或测试正在运行；暂停后才能开始新的清理测试。"
        else:
            message = (
                "已就绪。无需开启正式自动清理；点击后仍需确认风险，"
                "测试会真实整理物品，但不会修改正式功能开关。"
            )
        self.inventory_cleanup_test_status.setText(message)

    def _test_inventory_cleanup(self) -> None:
        if self.engine.is_monitoring():
            self.inventory_cleanup_test_status.setText(
                "请先暂停普通监测，再开始测试。"
            )
            return
        from .. import InventoryCleanupTestDialog

        dialog = InventoryCleanupTestDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self.inventory_cleanup_test_status.setText(
                "已取消，未执行任何游戏操作。"
            )
            return
        if self.engine.request_inventory_cleanup_test():
            self.inventory_cleanup_test_status.setText(
                "清理测试正在运行，请查看控制台状态和日志。"
            )
        self._sync_inventory_cleanup_debug_controls()

    def _fallback_delay_changed(self, value: float) -> None:
        self.engine.update_config(
            fallback_collect_delay_seconds=float(value)
        )
        if self.catch_strategy_combo.currentData() == "fixed_delay":
            self._sync_catch_strategy_controls()

    def _latest_collect_changed(self, value: float) -> None:
        self.engine.update_config(
            fixed_delay_latest_collect_seconds=float(value)
        )
        if self.catch_strategy_combo.currentData() == "fixed_delay":
            self._sync_catch_strategy_controls()

    def _sync_catch_strategy_controls(self) -> None:
        strategy = str(self.catch_strategy_combo.currentData())
        stack_index = {"stamina_bounce": 0, "fixed_delay": 1, "instant": 2}.get(strategy, 0)
        self.catch_option_stack.setCurrentIndex(stack_index)
        delay = float(self.fallback_delay_spin.value())
        latest = float(self.latest_collect_spin.value())
        effective = min(delay, latest)
        self.fixed_delay_effective_hint.setText(
            f"实际最晚会在上钩后 {effective:.1f} 秒按 Space；若目标更早消失，则按垃圾处理，不会拉钩。"
        )
        hints = {
            "stamina_bounce": "模式 1：先用 OK 特征确认中鱼图标并定位体力槽。中点连续变灰后，检测到填充宽度连续回升即可较早收杆；若识别失败后出现跑鱼提示，会学习本轮耗时并在下一轮提前 1–2 秒兜底。",
            "fixed_delay": f"模式 2（推荐）：目标仍存在时，等待 {delay:.1f} 秒收鱼，并以 {latest:.1f} 秒作为最迟拉钩上限；实际采用较早的 {effective:.1f} 秒。",
            "instant": "模式 3：只要识别到上钩鱼图标，立即按 Space 收杆。",
        }
        self.catch_strategy_hint.setText(hints.get(strategy, hints["stamina_bounce"]))
        self._sync_learned_escape_status()

    def _sync_learned_escape_status(self) -> None:
        learned = self.engine.config().learned_escape_seconds
        if learned <= 0:
            self.learned_escape_label.setText(
                "当前记录：尚未学习。识别到“讓牠跑掉了”后会自动记录本轮耗时。"
            )
            return
        target, margin = FishingEngine.learned_collect_timing(learned)
        self.learned_escape_label.setText(
            f"当前记录：上次跑鱼 {learned:.1f} 秒；识别仍失败时将在 "
            f"{target:.1f} 秒兜底（提前 {margin:.1f} 秒）。"
        )

    def _save_profile(self) -> None:
        config = self.engine.config()
        target = self.target_window_combo.currentData()
        target_handle = config.target_window_handle
        target_title = config.target_window_title
        if isinstance(target, window_target.WindowInfo):
            target_handle = target.handle
            target_title = target.title
        self.engine.update_config(
            monitor_index=int(self.monitor_combo.currentData() or 1),
            display_mode=str(self.mode_combo.currentData()),
            selected_resolution=self.resolution_combo.currentText(),
            capture_mode=str(self.target_mode_combo.currentData()),
            window_backend=str(self.window_backend_combo.currentData()),
            target_window_handle=target_handle,
            target_window_title=target_title,
        )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()
        self._refresh_calibration_summary()
        self._sync_floating_status_visibility()
    def _calibrate(self) -> None:
        self.calibration_summary.setText("校准待命：将鼠标停在钓鱼按钮正中心后按 F7，当前位置会立即记录，鼠标不会移动。")
        self._append_log("校准说明已显示：请把鼠标停在钓鱼按钮中心后按 F7；不要点击助手窗口来记录坐标。", EventKind.INFO)

    def _toggle_monitoring(self) -> None:
        self.engine.set_monitoring(not self.engine.is_monitoring())

