"""唯一监测线程和钓鱼帧状态分发"""
from __future__ import annotations

import mss
import time
from fishing_assistant.automation.models import (
    EventKind,
    IconState,
    StaminaBarSample,
    _OperationCancelled,
)
from fishing_assistant.config import AppConfig


class MonitorMixin:
    """唯一监测线程和钓鱼帧状态分发；由 FishingEngine 组装，不单独实例化。"""

    def _monitor_loop(self) -> None:
        screen: mss.MSS | None = None
        consecutive_failures = 0
        last_generation: int | None = None
        try:
            while not self._shutdown.is_set():
                if not self._enabled.wait(timeout=0.15):
                    consecutive_failures = 0
                    continue
                if self.is_paused():
                    self._shutdown.wait(0.10)
                    continue

                generation = self._interrupt_generation
                self._work_context.generation = generation
                if generation != last_generation:
                    consecutive_failures = 0
                    last_generation = generation
                config = self.config()
                if self._craft_request is not None:
                    from fishing_assistant.features.crafting.runner import run_crafting
                    request = self._craft_request
                    try:
                        run_crafting(self, request, generation)
                    except Exception as error:
                        if self._operation_active(generation):
                            request[0].stop(f"自动制作异常，已停止：{error}", error=True)
                            self._enabled.clear()
                            self._finish_fishing_session("automatic_error")
                            self._emit_crafting(request[0].progress(time.monotonic(), generation), log=True)
                        if self._craft_request is request and generation == self._interrupt_generation:
                            self._craft_request = None
                    continue
                if config.capture_mode == "window":
                    missing_calibration = config.target_button_offset is None
                else:
                    missing_calibration = config.button_center is None
                if missing_calibration:
                    self.set_monitoring(False)
                    continue
                source = (
                    "目标窗口"
                    if config.capture_mode == "window"
                    else "屏幕识别"
                )
                try:
                    self._ensure_operation_active()
                    if self._cleanup_test_requested.is_set():
                        self._cleanup_test_requested.clear()
                        self._perform_inventory_cleanup(
                            config,
                            1.0,
                            resume_fishing=False,
                        )
                        consecutive_failures = 0
                        continue
                    if config.capture_mode == "screen" and screen is None:
                        screen = mss.MSS()
                    frame = self._capture_frame(screen, config)
                    self._ensure_operation_active()
                    icon_state, signals = self.classify_frame_state(frame[:, :, :3], config)
                    self._ensure_operation_active()
                    loop_now = time.monotonic()
                    if config.v2_shadow_enabled:
                        self._shadow_observe(
                            frame[:, :, :3], icon_state, signals, screen, config
                        )
                    self._track_unrecognized(icon_state, loop_now, config)
                    strategy = self._catch_strategy(config)
                    stamina_sample = None
                    escape_message_confidence = 0.0
                    rod_required_confidence: float | None = None
                    inventory_full_confidence: float | None = None
                    if (
                        icon_state == IconState.FISH_HOOKED
                        or self._fish_resolution_pending
                        or self._waiting_for_clear
                    ):
                        # All catch strategies share result tracking for the stamina bar.
                        stamina_sample = self._capture_stamina_sample(
                            screen, config, loop_now
                        )
                    if (
                        strategy == "stamina_bounce"
                        and stamina_sample is None
                        and (
                            self._fish_resolution_pending
                            or self._escape_watch_until > loop_now
                        )
                    ):
                        escape_message_confidence = (
                            self._capture_escape_message_confidence(
                                screen, config, loop_now
                            )
                        )
                    if (
                        icon_state not in (IconState.WAITING_BITE, IconState.FISH_HOOKED)
                        and self._should_scan_blocking_messages()
                    ):
                        blocking_confidences = (
                            self._capture_blocking_message_confidences(
                                screen, config, loop_now
                            )
                        )
                        if blocking_confidences is not None:
                            (
                                rod_required_confidence,
                                inventory_full_confidence,
                            ) = blocking_confidences
                    self._ensure_operation_active()
                    self._process_frame(
                        signals.red_pixels,
                        config,
                        icon_state,
                        stamina_sample,
                        escape_message_confidence,
                        rod_required_confidence,
                        inventory_full_confidence,
                        signals.recognition_source,
                        signals.recognition_confidence,
                    )
                    if consecutive_failures and self._operation_active(generation):
                        self._emit(
                            EventKind.SUCCESS,
                            f"{source}已恢复，连续失败计数已清零。",
                            monitoring=True,
                        )
                    consecutive_failures = 0
                except _OperationCancelled:
                    consecutive_failures = 0
                    continue
                except Exception as error:  # pragma: no cover - 显示器环境差异
                    # 暂停/重启期间返回的截图异常不再播报，也不能停止新一轮运行。
                    if not self._operation_active(generation):
                        consecutive_failures = 0
                        continue
                    retry_limit = max(
                        0, min(20, config.runtime_error_retry_count)
                    )
                    if consecutive_failures < retry_limit:
                        consecutive_failures += 1
                        if (
                            config.capture_mode == "window"
                            and config.window_backend == "ok"
                        ):
                            self._close_ok_window_backend()
                        if screen is not None:
                            try:
                                screen.close()
                            finally:
                                screen = None
                        delay = min(
                            self.MONITOR_RETRY_MAX_DELAY_SECONDS,
                            0.25 * (2 ** (consecutive_failures - 1)),
                        )
                        self._emit(
                            EventKind.WARNING,
                            f"{source}临时失败：{error}；{delay:.2f} 秒后自动重试 "
                            f"({consecutive_failures}/{retry_limit})。",
                            monitoring=True,
                        )
                        time.sleep(delay)
                    else:
                        total_failures = consecutive_failures + 1
                        self._enabled.clear()
                        self._finish_fishing_session("recognition_error")
                        self._emit(
                            EventKind.ERROR,
                            f"{source}已暂停：连续失败 {total_failures} 次，"
                            f"已用完 {retry_limit} 次自动重试：{error}",
                        )
                        consecutive_failures = 0
                # 配置文件可能被手改成非法值；负数会让 sleep 抛异常杀死本线程。
                # 上钩期间体力扫描自带节流，主循环改用短睡眠保住反弹采样节奏。
                if self._fish_resolution_pending:
                    time.sleep(self.PENDING_RESOLUTION_POLL_SECONDS)
                else:
                    time.sleep(max(0, config.poll_interval_ms) / 1000)
        except Exception as error:  # pragma: no cover - mss 初始化失败
            # 线程即将退出；必须同步清掉监测标志，避免界面停留在“监测中”假状态。
            self._enabled.clear()
            self._finish_fishing_session("monitor_start_error")
            self._emit(EventKind.ERROR, f"无法启动识别服务：{error}")
        finally:
            self._work_context.generation = None
            if screen is not None:
                screen.close()

    def _process_frame(
        self,
        red_pixels: int,
        config: AppConfig,
        icon_state: IconState | None = None,
        stamina_sample: StaminaBarSample | None = None,
        escape_message_confidence: float = 0.0,
        rod_required_confidence: float | None = None,
        inventory_full_confidence: float | None = None,
        recognition_source: str | None = None,
        recognition_confidence: float = 0.0,
    ) -> None:
        self._ensure_operation_active()
        if recognition_source is None:
            recognition_source = (
                "compat_pixel"
                if config.recognition_backend == "pixel"
                else "ok_feature"
            )
        if icon_state is None:
            icon_state = (
                self.classify_icon_state(red_pixels, config)
                if config.recognition_backend == "pixel"
                else IconState.NORMAL
            )
        fish_visible = icon_state == IconState.FISH_HOOKED
        now = time.monotonic()

        if (
            icon_state != self._last_logged_icon_state
            or recognition_source != self._last_logged_recognition_source
        ):
            state_name = {
                IconState.NORMAL: "未分类普通图标",
                IconState.READY_TO_CAST: "可抛竿鱼竿图标",
                IconState.WAITING_BITE: "等待上钩图标",
                IconState.FISH_HOOKED: "上钩图标",
                IconState.IDLE_RECOVERY: "指南针图标",
                IconState.HORSE_MOUNT_PROMPT: "骑马图标",
                IconState.HORSE_DISMOUNT_PROMPT: "下马图标",
            }[icon_state]
            if recognition_source == "ok_feature":
                recognition_detail = (
                    f"OK 特征，相似度 {recognition_confidence:.3f}"
                )
            elif recognition_source == "compass_pixel":
                recognition_detail = (
                    "指南针像素校正，"
                    f"中心黑点匹配度 {recognition_confidence * 100:.1f}%"
                )
            elif recognition_source == "v2_signature":
                recognition_detail = (
                    f"v2 颜色签名，判别余裕 {recognition_confidence:.3f}"
                )
            else:
                recognition_detail = (
                    "兼容像素，"
                    f"红色像素 {red_pixels}，阈值 {config.fish_red_pixel_threshold}"
                )
            self._emit(
                EventKind.INFO,
                f"图标状态切换为“{state_name}”：识别来源 {recognition_detail}，"
                f"连续上钩帧 {self._red_frames + (1 if fish_visible else 0)}。",
                monitoring=True,
            )
            self._last_logged_icon_state = icon_state
            self._last_logged_recognition_source = recognition_source

        if icon_state in (IconState.WAITING_BITE, IconState.FISH_HOOKED):
            self._clear_failed_start_tracking()
        elif self._handle_blocking_messages(
            rod_required_confidence, inventory_full_confidence, config
        ):
            return

        if self._handle_horse_icon(icon_state, config, now):
            return
        if now < self._horse_settle_until:
            return

        if fish_visible:
            self._red_frames += 1
            self._clear_frames = 0
            self._idle_frames = 0
        else:
            self._red_frames = 0
            self._clear_frames += 1
            if icon_state == IconState.IDLE_RECOVERY:
                self._idle_frames += 1
            else:
                self._idle_frames = 0

        if self._startup_probe_active:
            if icon_state == IconState.READY_TO_CAST:
                self._startup_probe_active = False
                self._emit(
                    EventKind.INFO,
                    "启动探测识别到开始钓鱼图标，准备直接按 Space。",
                    monitoring=True,
                )
            elif icon_state in (IconState.WAITING_BITE, IconState.FISH_HOOKED):
                self._startup_probe_active = False
                self._pending_recast_at = None
                self._pending_recast_reason = ""
                self._emit(
                    EventKind.INFO,
                    "启动探测确认当前已经在钓鱼，不发送额外按键。",
                    monitoring=True,
                )
            elif (
                config.auto_recover_idle
                and icon_state == IconState.IDLE_RECOVERY
                and self._idle_frames
                >= min(
                    self.STARTUP_IDLE_CONFIRM_FRAMES,
                    max(1, config.recovery_consecutive_frames),
                )
            ):
                self._startup_probe_active = False
                self._recover_idle_state(config, startup=True)
                self._schedule_recast(
                    time.monotonic(), config, "启动指南针移动恢复完成"
                )
                return

        if (
            not self._waiting_for_clear
            and escape_message_confidence >= self.ESCAPE_MESSAGE_MATCH_THRESHOLD
            and self._record_escape_failure(
                now, config, escape_message_confidence
            )
        ):
            self._perform_pending_recast(now, icon_state, config)
            return
        if self._escape_watch_until:
            if icon_state == IconState.READY_TO_CAST:
                self._finish_escape_watch(now, config, ready_visible=True)
            elif now >= self._escape_watch_until:
                self._finish_escape_watch(now, config)

        if stamina_sample is not None and (
            self._fish_resolution_pending or self._waiting_for_clear
        ):
            self._clear_frames = 0
            self._observe_stamina_bar(stamina_sample)

        if self._waiting_for_clear:
            # 收杆后游戏会短暂直接恢复“可抛竿”图标。它是比普通清空帧
            # 更强的正向证据：首帧命中就立即续钓，避免 OK 全尺度扫描较慢
            # 时错过短暂图标，随后误等到指南针并执行不必要的 W → S。
            stamina_gone = (
                self._fish_round_had_stamina
                and now - self._fish_round_last_stamina_at
                >= self.STAMINA_LOST_GRACE_SECONDS
            )
            if icon_state == IconState.READY_TO_CAST and (
                stamina_gone or not self._fish_round_had_stamina
            ):
                self._finish_collected_fishing_round()
                self._schedule_recast(now, config, "收鱼完成，钓鱼图标已恢复")
            elif (
                self._clear_frames >= config.clear_consecutive_frames
                and (stamina_gone or not self._fish_round_had_stamina)
            ):
                self._finish_collected_fishing_round()
                self._schedule_recast(now, config, "收鱼完成")
        elif self._fish_resolution_pending:
            strategy = self._catch_strategy(config)
            if strategy == "instant" and fish_visible:
                # 上钩等待期间被切换成模式 3：立即收杆，而不是楔在
                # 只认识模式 1 / 模式 2 的分支里直到本轮目标消失。
                self._collect_fish(
                    now, config, "收鱼策略已切换为模式 3，检测到上钩立即收杆。"
                )
            elif strategy == "stamina_bounce":
                if stamina_sample is not None:
                    if self._fish_round_rebounded:
                        self._collect_fish(
                            now,
                            config,
                            "体力条中点已由灰色连续恢复为绿色；已按 Space 收鱼。",
                        )
                stamina_reference_at = (
                    self._last_stamina_seen_at
                    or self._hook_started_at
                    or now
                )
                if (
                    self._fish_resolution_pending
                    and stamina_sample is None
                    and not fish_visible
                    and self._clear_frames >= config.clear_consecutive_frames
                    and now - stamina_reference_at
                    >= self.STAMINA_LOST_GRACE_SECONDS
                ):
                    self._start_escape_watch(now)
                    if icon_state == IconState.READY_TO_CAST:
                        self._finish_escape_watch(
                            now, config, ready_visible=True
                        )
                elif (
                    self._fish_resolution_pending
                    and self._learned_collect_due(now, config)
                ):
                    target, margin = self.learned_collect_timing(
                        config.learned_escape_seconds
                    )
                    self._collect_fish(
                        now,
                        config,
                        f"体力条未完成中点灰→绿确认，已按跑鱼学习时间 {target:.1f} 秒兜底收杆（提前 {margin:.1f} 秒）。",
                        allow_without_stamina=True,
                    )
            elif not fish_visible and self._clear_frames >= config.clear_consecutive_frames:
                if (
                    self._fish_round_had_stamina
                    and self._last_stamina_seen_at
                    and now - self._last_stamina_seen_at
                    >= self.STAMINA_LOST_GRACE_SECONDS
                ):
                    self._finish_uncollected_fishing_round()
                else:
                    self._fish_resolution_pending = False
                    self._reset_stamina_tracking()
                    self._reset_fishing_round_tracking()
                    self._emit(
                        EventKind.WARNING,
                        "钓鱼目标已消失，但本轮未确认体力条变化；"
                        "为避免误分类，未计入上鱼成功、普通成功或失败。",
                        monitoring=True,
                    )
                self._schedule_recast(now, config, "计时目标已消失")
            elif fish_visible and strategy == "fixed_delay":
                hook_started = self._hook_started_at or now
                wait_seconds, latest_seconds, collect_after = (
                    self.fixed_delay_timing(config)
                )
                if now - hook_started >= collect_after:
                    message = (
                        f"模式 2 已到最迟拉钩时间 {latest_seconds:.1f} 秒，已按 Space 收鱼。"
                        if latest_seconds < wait_seconds
                        else f"模式 2 等待 {wait_seconds:.1f} 秒完成，已按 Space 收鱼。"
                    )
                    self._collect_fish(now, config, message)
        elif (
            fish_visible
            and self._red_frames >= config.trigger_consecutive_frames
            and now - self._last_press_at >= config.press_cooldown_ms / 1000
        ):
            self._begin_fish_resolution(now, config, stamina_sample)

        idle_recovery_ready = (
            config.auto_recover_idle
            and icon_state == IconState.IDLE_RECOVERY
            and self._idle_frames >= config.recovery_consecutive_frames
            and not self._waiting_for_clear
            and not self._fish_resolution_pending
            and not self._escape_watch_until
            and now - self._last_press_at >= self.CAST_TRANSITION_GRACE_SECONDS
        )
        if idle_recovery_ready:
            recovery_limit = max(1, min(20, int(config.recovery_attempt_limit)))
            if (
                self._recovery_attempts_without_success >= recovery_limit
                and now - self._last_recovery_at
                >= self.CAST_TRANSITION_GRACE_SECONDS
            ):
                self._stop_after_recovery_limit(recovery_limit)
                return
            if (
                self._recovery_attempts_without_success < recovery_limit
                and now - self._last_recovery_at
                >= config.recovery_cooldown_ms / 1000
            ):
                self._recover_idle_state(config)
                self._schedule_recast(time.monotonic(), config, "移动恢复完成")

        self._perform_pending_recast(now, icon_state, config)
        self._ensure_operation_active()

        if now - self._last_metric_at >= 0.18:
            self._emit(
                EventKind.METRIC,
                self._metric_message(icon_state, now, config),
                red_pixels=red_pixels,
                recognition_source=recognition_source,
                recognition_confidence=recognition_confidence,
                fish_visible=fish_visible,
                monitoring=True,
                icon_state=icon_state,
                stamina_fill_width=self._stamina_last_width,
                stamina_peak_width=self._stamina_peak_width,
                waiting_for_bounce=self._fish_resolution_pending,
                catch_strategy=self._catch_strategy(config),
                hook_elapsed_seconds=(
                    max(0.0, now - self._hook_started_at)
                    if self._hook_started_at is not None
                    else 0.0
                ),
            )
            self._last_metric_at = now
