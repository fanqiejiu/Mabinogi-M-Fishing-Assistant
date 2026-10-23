"""骑马保护、阻断提示、续钓及 W/S 移动恢复"""
from __future__ import annotations

import time
from fishing_assistant.automation.models import EventKind, IconState
from fishing_assistant.config import AppConfig


class RecoveryMixin:
    """骑马保护、阻断提示、续钓及 W/S 移动恢复；由 FishingEngine 组装，不单独实例化。"""

    def _handle_horse_icon(
        self, icon_state: IconState, config: AppConfig, now: float
    ) -> bool:
        """防止续钓误按 Space 上马；已经上马时只尝试一次下马。"""
        if icon_state == IconState.HORSE_MOUNT_PROMPT:
            self._horse_mount_frames += 1
            self._horse_dismount_frames = 0
            if self._horse_mount_frames < 2:
                return True
            self._cancel_pending_recast()
            if self._horse_guard_state != icon_state:
                self._emit(EventKind.WARNING, "检测到骑马图标，已阻止自动按 Space 上马。")
            self._horse_guard_state = icon_state
            return True

        if icon_state == IconState.HORSE_DISMOUNT_PROMPT:
            self._horse_dismount_frames += 1
            self._horse_mount_frames = 0
            if self._horse_dismount_frames < 2:
                return True
            self._cancel_pending_recast()
            # 同一段持续显示的下马提示只按一次；提示消失又出现才允许重试。
            if (
                not self._horse_dismount_attempted
                and now - self._last_horse_dismount_at >= 2.0
            ):
                self._press_key("space", config)
                self._horse_dismount_attempted = True
                self._last_horse_dismount_at = now
                self._horse_settle_until = now + 1.5
                self._emit(EventKind.SUCCESS, "检测到下马图标，已按一次 Space 下马，等待钓鱼图标恢复。")
            self._horse_guard_state = icon_state
            return True

        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state = None
        self._horse_dismount_attempted = False
        return False

    def _should_scan_blocking_messages(self) -> bool:
        return (
            self._unconfirmed_cast_attempts >= self.BLOCKING_MESSAGE_RETRY_THRESHOLD
            or self._recovery_attempts_without_success
            >= self.BLOCKING_MESSAGE_RETRY_THRESHOLD
        )

    def _announce_blocking_message_scan_if_needed(self) -> None:
        if not self._should_scan_blocking_messages() or self._blocking_message_scan_announced:
            return
        self._blocking_message_scan_announced = True
        self._emit(
            EventKind.WARNING,
            "多次尝试后仍未进入等待上钩状态，开始通过 OK 检查画面上方的鱼竿和背包提示。",
            monitoring=True,
        )

    def _clear_failed_start_tracking(self) -> None:
        self._unconfirmed_cast_attempts = 0
        self._recovery_attempts_without_success = 0
        self._rod_required_hits = 0
        self._inventory_full_hits = 0
        self._blocking_message_scan_announced = False
        self._last_blocking_message_scan_at = 0.0

    def _handle_blocking_messages(
        self,
        rod_confidence: float | None,
        inventory_confidence: float | None,
        config: AppConfig | None = None,
    ) -> bool:
        if rod_confidence is not None:
            if rod_confidence >= self.ROD_REQUIRED_MATCH_THRESHOLD:
                self._rod_required_hits += 1
            else:
                self._rod_required_hits = 0
        if inventory_confidence is not None:
            if inventory_confidence >= self.INVENTORY_FULL_MATCH_THRESHOLD:
                self._inventory_full_hits += 1
            else:
                self._inventory_full_hits = 0

        confirmed: list[tuple[str, float]] = []
        if (
            rod_confidence is not None
            and self._rod_required_hits >= self.BLOCKING_MESSAGE_CONFIRM_FRAMES
        ):
            confirmed.append(("rod_required", rod_confidence))
        if (
            inventory_confidence is not None
            and self._inventory_full_hits >= self.BLOCKING_MESSAGE_CONFIRM_FRAMES
        ):
            confirmed.append(("inventory_full", inventory_confidence))
        if not confirmed:
            return False

        # 早退后的相似度只保证过阈值、彼此不可比较：用固定优先序
        # （钓竿优先），不按分数排序。
        message_kind, confidence = confirmed[0]
        if (
            message_kind == "inventory_full"
            and config is not None
            and config.inventory_auto_cleanup_enabled
        ):
            return self._perform_inventory_cleanup(config, confidence)
        return self._stop_for_blocking_message(message_kind, confidence)

    def _stop_for_blocking_message(self, message_kind: str, confidence: float) -> bool:
        cast_attempts = self._unconfirmed_cast_attempts
        recovery_attempts = self._recovery_attempts_without_success
        self._enabled.clear()
        self._finish_fishing_session("blocking_game_prompt")
        self._reset_detection()

        if message_kind == "inventory_full":
            detail = (
                "检测到游戏提示“請整理背包後再試一次。”，背包已经装满。"
                "监测已停止；请整理背包后再按 F8。"
            )
        else:
            detail = (
                "检测到游戏提示“必須配戴釣竿。”，鱼竿耐久度可能已经耗尽，"
                "或当前没有装备鱼竿。监测已停止；请更换或装备鱼竿后再按 F8。"
            )
        self._emit(
            EventKind.ERROR,
            detail
            + f"本轮自动抛竿 {cast_attempts} 次，移动恢复 {recovery_attempts} 次，"
            + f"OK 特征相似度 {confidence:.3f}。",
            monitoring=False,
        )
        return True

    def _stop_after_recovery_limit(self, recovery_limit: int) -> None:
        attempts = self._recovery_attempts_without_success
        self._interrupt_generation += 1
        self._enabled.clear()
        self._finish_fishing_session("recovery_limit")
        self._reset_detection()
        self._emit(
            EventKind.ERROR,
            f"连续移动恢复 {attempts} 次（上限 {recovery_limit} 次）仍未进入等待上钩状态，"
            "可能已经离开钓鱼区域。监测已停止；请回到钓鱼点后重新校准并按 F8。",
            monitoring=False,
        )

    def _cancel_pending_recast(self) -> None:
        self._waiting_for_clear = False
        self._fish_resolution_pending = False
        self._clear_escape_watch()
        self._reset_stamina_tracking()
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._refresh_hover_before_recast = False

    def _schedule_recast(self, now: float, config: AppConfig, reason: str) -> None:
        if not config.auto_resume_fishing:
            self._emit(EventKind.INFO, f"{reason}，等待手动按 Space 再次钓鱼。")
            return
        self._pending_recast_at = now
        self._pending_recast_reason = reason
        self._emit(
            EventKind.INFO,
            f"{reason}，正在等待可抛竿鱼竿图标；图标出现后立即按 Space。",
        )

    def _perform_pending_recast(
        self, now: float, icon_state: IconState, config: AppConfig
    ) -> None:
        if self._pending_recast_at is None:
            return
        # 帧首快照与实时设置任一显示已关闭都撤销：用户可能在本帧
        # 处理期间才取消自动续钓，送键前必须以实时设置为准。
        if not config.auto_resume_fishing or not self.config().auto_resume_fishing:
            self._pending_recast_at = None
            self._pending_recast_reason = ""
            self._refresh_hover_before_recast = False
            return
        if icon_state != IconState.READY_TO_CAST:
            return
        if self._refresh_hover_before_recast:
            self._refresh_background_hover(config)
            self._refresh_hover_before_recast = False
        self._press_key("space", config)
        self._last_press_at = now
        reason = self._pending_recast_reason
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._unconfirmed_cast_attempts += 1
        self._emit(EventKind.SUCCESS, f"{reason}，已按 Space 重新开始钓鱼。", monitoring=True)
        self._announce_blocking_message_scan_if_needed()

    def _recover_idle_state(
        self, config: AppConfig, *, startup: bool = False
    ) -> None:
        """识别到指南针时按所选方式移动，刷新开始钓鱼图标。"""
        self._ensure_operation_active()
        self._last_recovery_at = time.monotonic()
        self._idle_frames = 0
        was_enabled = self._enabled.is_set()
        generation = self._interrupt_generation

        def interrupted() -> bool:
            return was_enabled and (
                not self._enabled.is_set()
                or self._shutdown.is_set()
                # 代数比对能识破「停止后又立刻重启」的 ABA 情形。
                or generation != self._interrupt_generation
            )

        mode = self._recovery_movement_mode(config)
        compensation_taps = 0
        if mode == "w_only":
            w_only_count = max(1, min(20, int(config.recovery_w_only_count)))
            w_only_hold_seconds = max(
                0.1, min(5.0, float(config.recovery_w_only_hold_seconds))
            )
            w_only_hold_ms = round(w_only_hold_seconds * 1000)
            for tap_index in range(w_only_count):
                if tap_index:
                    time.sleep(config.recovery_pause_ms / 1000)
                    if interrupted():
                        self._emit(
                            EventKind.WARNING,
                            "仅 W 恢复已被停止中断，未发送后续 W。",
                        )
                        return
                self._tap_key("w", w_only_hold_ms, config)
                if interrupted():
                    self._emit(
                        EventKind.WARNING,
                        "仅 W 恢复已被停止中断，未发送后续 W。",
                    )
                    return
            self._recovery_attempts_without_success += 1
            message = (
                "启动时识别到指南针图标，"
                if startup
                else "检测到指南针状态，"
            )
            message += (
                f"已仅按 W {w_only_count} 次，每次长按 {w_only_hold_seconds:.1f} 秒。"
            )
        else:
            self._tap_key("w", config.recovery_key_hold_ms, config)
            time.sleep(config.recovery_pause_ms / 1000)
            if interrupted():
                # Esc / 暂停必须是可靠的送键取消边界：W 之后的停顿期间
                # 被停止时，不再补送 S（焦点可能已切到其他程序）。
                self._emit(
                    EventKind.WARNING, "恢复序列已被停止中断，未发送后续按键。"
                )
                return
            self._tap_key("s", config.recovery_key_hold_ms, config)
            if interrupted():
                self._emit(
                    EventKind.WARNING,
                    "恢复序列已被停止中断，已取消向前补偿。",
                )
                return
            self._recovery_attempts_without_success += 1
            compensation_interval = max(
                0, min(20, int(config.recovery_forward_compensation_interval))
            )
            configured_taps = max(
                1, min(10, int(config.recovery_forward_compensation_taps))
            )
            if (
                compensation_interval > 0
                and self._recovery_attempts_without_success % compensation_interval == 0
            ):
                for _tap_index in range(configured_taps):
                    time.sleep(config.recovery_pause_ms / 1000)
                    if interrupted():
                        self._emit(
                            EventKind.WARNING,
                            "向前补偿序列已被停止中断，未发送后续 W。",
                        )
                        return
                    self._tap_key("w", config.recovery_key_hold_ms, config)
                    compensation_taps += 1
                    if interrupted():
                        self._emit(
                            EventKind.WARNING,
                            "向前补偿序列已被停止中断，未发送后续 W。",
                        )
                        return
            message = (
                "启动时识别到指南针图标，已执行 W → S 移动恢复。"
                if startup
                else "检测到指南针状态，已执行 W → S 移动恢复。"
            )
            if compensation_taps:
                message = (
                    f"{message[:-1]}；第 {self._recovery_attempts_without_success} 次恢复"
                    f"已额外短按 W {compensation_taps} 次进行向前补偿。"
                )
        if config.capture_mode == "window" and config.auto_resume_fishing:
            self._refresh_hover_before_recast = True
        self._emit(EventKind.SUCCESS, message, monitoring=True)
        self._announce_blocking_message_scan_if_needed()
