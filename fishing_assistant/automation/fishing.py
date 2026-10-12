"""三种收杆策略、计时学习与体力反弹状态机"""
from __future__ import annotations

import pyautogui
import time
from fishing_assistant import window_target
from fishing_assistant.automation.models import (
    EventKind,
    FishingResult,
    IconState,
    StaminaBarSample,
    StaminaMidpointState,
)
from fishing_assistant.config import AppConfig, effective_roi_size
from fishing_assistant.diagnostics import record_error


class FishingFlowMixin:
    """三种收杆策略、计时学习与体力反弹状态机；由 FishingEngine 组装，不单独实例化。"""

    @staticmethod
    def _catch_strategy(config: AppConfig) -> str:
        if config.catch_strategy in {"fixed_delay", "instant"}:
            return config.catch_strategy
        return "stamina_bounce"

    @staticmethod
    def _recovery_movement_mode(config: AppConfig) -> str:
        return "w_only" if config.recovery_movement_mode == "w_only" else "ws"

    @staticmethod
    def fixed_delay_timing(config: AppConfig) -> tuple[float, float, float]:
        """返回模式二的等待、最迟拉钩和实际执行秒数。"""
        wait_seconds = max(0.0, float(config.fallback_collect_delay_seconds))
        latest_seconds = max(
            0.0, float(config.fixed_delay_latest_collect_seconds)
        )
        return wait_seconds, latest_seconds, min(wait_seconds, latest_seconds)

    def _monitoring_details(self, config: AppConfig) -> str:
        """输出一条足以复现当前识别环境的启动日志。"""
        strategy = {
            "stamina_bounce": "模式 1：中点灰→绿确认",
            "fixed_delay": (
                f"模式 2（推荐，等待 {config.fallback_collect_delay_seconds:.1f} 秒，"
                f"最迟 {config.fixed_delay_latest_collect_seconds:.1f} 秒）"
            ),
            "instant": "模式 3（上钩立即收杆）",
        }[self._catch_strategy(config)]
        icon_recognizer = (
            "OK FeatureSet + 指南针中心黑点校正"
            if config.recognition_backend != "pixel"
            else "旧版像素兼容模式"
        )
        pixel_detail = (
            f"；鱼体阈值 {config.fish_red_pixel_threshold} px"
            if config.recognition_backend == "pixel"
            else ""
        )
        source_resolution = None
        if config.capture_mode == "window":
            try:
                target = self._resolve_target_window(config)
                source_resolution = (target.width, target.height)
            except Exception:
                pass
        roi_width, roi_height = effective_roi_size(config, source_resolution)
        roi_mode = "自动" if config.auto_scale_roi else "手动"
        if self._recovery_movement_mode(config) == "w_only":
            recovery_detail = (
                f"仅 W {config.recovery_w_only_count} 次 × "
                f"{config.recovery_w_only_hold_seconds:.1f} 秒"
            )
        else:
            forward_compensation = (
                "关闭"
                if config.recovery_forward_compensation_interval <= 0
                else (
                    f"每 {config.recovery_forward_compensation_interval} 次恢复"
                    f"补按 W {config.recovery_forward_compensation_taps} 次"
                )
            )
            recovery_detail = f"W → S；向前补偿 {forward_compensation}"
        common = (
            f"策略 {strategy}；图标识别 {icon_recognizer}；"
            "异常提示识别 OK FeatureSet；"
            f"识别区域 {roi_mode} {roi_width}×{roi_height}；"
            f"轮询 {config.poll_interval_ms} ms；"
            f"临时错误重试 {config.runtime_error_retry_count} 次；"
            f"移动恢复 {recovery_detail}；"
            f"恢复上限 {config.recovery_attempt_limit} 次{pixel_detail}。"
        )
        if config.capture_mode == "window":
            backend = "Windows Graphics Capture（WGC）" if config.window_backend == "ok" else "PrintWindow"
            return (
                f"启动参数：后台运行，目标窗口“{config.target_window_title or '未命名'}”；捕获方式 {backend}；输入方式 PostMessage；"
                + common
            )
        center = config.button_center or (0, 0)
        return f"启动参数：屏幕坐标 {center}，显示器 {config.monitor_index}；" + common

    def _prepare_stamina_view(self, config: AppConfig) -> None:
        """模式一启动时向上滚轮拉近角色，方便识别角色头顶体力条。"""
        if self._catch_strategy(config) != "stamina_bounce":
            return
        steps = max(0, min(12, config.stamina_zoom_in_steps))
        if steps == 0:
            self._emit(EventKind.INFO, "模式一镜头拉近已关闭（滚轮次数为 0）。")
            return
        try:
            if config.capture_mode == "window":
                target = self._resolve_target_window(config)
            else:
                target = window_target.find_mabinogi_mobile_window(
                    window_target.list_target_windows()
                )
                if target is None:
                    raise RuntimeError("未找到标题为“瑪奇 Mobile”的游戏窗口。")
            # 该游戏忽略后台 WM_MOUSEWHEEL；短暂激活后发送真实滚轮，光标坐标不会改变。
            window_target.activate_window(target.handle)
            time.sleep(0.12)
            pyautogui.scroll(steps)
            self._emit(
                EventKind.INFO,
                f"模式一已短暂切到“{target.title}”并发送真实向上滚轮 {steps} 格；鼠标位置保持不变，游戏画面应已放大。",
            )
        except Exception as error:  # pragma: no cover - 由实际窗口消息兼容性决定
            self._emit(EventKind.WARNING, f"模式一镜头拉近失败，可在游戏内手动向上滚轮：{error}")

    def _begin_fish_resolution(
        self,
        now: float,
        config: AppConfig,
        stamina_sample: StaminaBarSample | None,
    ) -> None:
        self._clear_escape_watch()
        self._fish_resolution_pending = True
        self._reset_stamina_tracking()
        self._reset_fishing_round_tracking()
        self._hook_started_at = now
        self._observe_stamina_bar(stamina_sample)
        strategy = self._catch_strategy(config)
        if strategy == "instant":
            self._collect_fish(now, config, "模式 3：检测到上钩图标，已立即按 Space 收杆。")
            return
        if strategy == "fixed_delay":
            wait_seconds, latest_seconds, collect_after = self.fixed_delay_timing(
                config
            )
            self._emit(
                EventKind.INFO,
                f"检测到上钩，模式 2 开始计时：等待 {wait_seconds:.1f} 秒，"
                f"最迟 {latest_seconds:.1f} 秒拉钩；本轮将在 {collect_after:.1f} 秒收杆。",
                monitoring=True,
            )
            return
        learned_hint = ""
        if config.learned_escape_seconds > 0:
            target, margin = self.learned_collect_timing(
                config.learned_escape_seconds
            )
            learned_hint = (
                f" 若中点灰→绿识别仍失败，将按已学习的 {target:.1f} 秒"
                f"兜底收杆（比上次跑鱼提前 {margin:.1f} 秒）。"
            )
        self._emit(
            EventKind.INFO,
            "检测到上钩，正在追踪绿色体力条；中点连续变灰后只记录，"
            "必须再次连续恢复绿色才收鱼。" + learned_hint,
            monitoring=True,
        )
        if stamina_sample is None:
            fallback = (
                "若后续仍找不到，将使用已学习的跑鱼时间兜底。"
                if config.learned_escape_seconds > 0
                else "本轮先不盲目收杆；跑鱼后会扫描提示文字并学习耗时。"
            )
            self._emit(
                EventKind.INFO,
                "模式一安全门：尚未找到体力条。" + fallback,
                monitoring=True,
            )

    def _collect_fish(
        self,
        now: float,
        config: AppConfig,
        message: str,
        *,
        allow_without_stamina: bool = False,
    ) -> None:
        if (
            self._catch_strategy(config) == "stamina_bounce"
            and not self._stamina_bar_seen
            and not allow_without_stamina
        ):
            self._fish_resolution_pending = False
            self._reset_stamina_tracking()
            self._emit(
                EventKind.WARNING,
                "模式一安全保护：未确认角色体力条，已阻止本次 Space 收杆。",
                monitoring=True,
            )
            return
        self._press_key("space", config)
        self._last_press_at = now
        self._fish_round_collect_pressed = True
        self._fish_resolution_pending = False
        self._waiting_for_clear = True
        self._clear_escape_watch()
        self._reset_stamina_tracking()
        self._emit(EventKind.SUCCESS, message, monitoring=True)

    @staticmethod
    def learned_collect_timing(failure_seconds: float) -> tuple[float, float]:
        """根据跑鱼耗时生成提前 1–2 秒的下一轮兜底收杆时间。"""
        if failure_seconds <= 0:
            return 0.0, 0.0
        margin = min(2.0, max(1.0, failure_seconds * 0.10))
        return max(1.0, failure_seconds - margin), margin

    def _learned_collect_due(self, now: float, config: AppConfig) -> bool:
        if self._hook_started_at is None or config.learned_escape_seconds <= 0:
            return False
        target, _margin = self.learned_collect_timing(
            config.learned_escape_seconds
        )
        return now - self._hook_started_at >= target

    def _start_escape_watch(self, now: float) -> None:
        elapsed = (
            max(0.0, now - self._hook_started_at)
            if self._hook_started_at is not None
            else 0.0
        )
        self._escape_candidate_elapsed = elapsed
        self._escape_candidate_stamina_seen = self._stamina_bar_seen
        self._escape_watch_until = now + self.ESCAPE_MESSAGE_WATCH_SECONDS
        self._fish_resolution_pending = False
        self._reset_stamina_tracking()
        self._emit(
            EventKind.INFO,
            f"上钩图标在 {elapsed:.1f} 秒后消失；继续扫描跑鱼提示 "
            f"{self.ESCAPE_MESSAGE_WATCH_SECONDS:.1f} 秒，再判断失败或垃圾。",
            monitoring=True,
        )

    def _record_escape_failure(
        self, now: float, config: AppConfig, confidence: float
    ) -> bool:
        if self._escape_message_latched:
            return False
        if self._fish_resolution_pending and self._hook_started_at is not None:
            elapsed = max(0.0, now - self._hook_started_at)
        elif self._escape_watch_until and self._escape_candidate_elapsed > 0:
            elapsed = self._escape_candidate_elapsed
        else:
            return False
        if elapsed < 1.0:
            return False

        self._escape_message_latched = True
        self._fish_resolution_pending = False
        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        self._reset_stamina_tracking()

        self._record_fishing_session_result(FishingResult.FAILURE)
        self._reset_fishing_round_tracking()
        learned_seconds = round(elapsed, 2)
        self.update_config(learned_escape_seconds=learned_seconds)
        target, margin = self.learned_collect_timing(learned_seconds)
        message = (
            f"检测到“猶豫了一下，結果讓牠跑掉了”：本轮上钩后 "
            f"{elapsed:.1f} 秒失败。已记录时间；下一次若绿条仍未完成中点灰→绿确认，"
            f"将在 {target:.1f} 秒兜底收杆（提前 {margin:.1f} 秒）。"
        )
        record_error(
            "fish escaped learning",
            message,
            extra={
                "failure_seconds": round(elapsed, 3),
                "learned_collect_seconds": round(target, 3),
                "advance_seconds": round(margin, 3),
                "template_confidence": round(confidence, 4),
            },
        )
        self._emit(EventKind.WARNING, message, monitoring=True)
        self._schedule_recast(now, config, "已记录本次跑鱼失败")
        return True

    def _finish_escape_watch(
        self,
        now: float,
        config: AppConfig,
        *,
        ready_visible: bool = False,
    ) -> None:
        stamina_seen = self._fish_round_had_stamina
        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        if stamina_seen:
            self._finish_uncollected_fishing_round()
        if ready_visible:
            self._schedule_recast(
                now, config, "可抛竿鱼竿图标已恢复"
            )
        elif stamina_seen:
            self._schedule_recast(
                now, config, "未出现跑鱼文字，体力条也未完成中点灰→绿确认，已跳过本次目标"
            )
        else:
            self._emit(
                EventKind.WARNING,
                "上钩候选消失后未识别到体力条或跑鱼提示；判为误识别，不发送 Space 也不自动续钓。",
                monitoring=True,
            )

    def _clear_escape_watch(self) -> None:
        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        self._escape_message_latched = False
        self._last_escape_scan_at = 0.0

    def _observe_stamina_bar(self, sample: StaminaBarSample | None) -> bool:
        if sample is None:
            return False
        self._fish_round_had_stamina = True
        if not self._fish_round_depleted:
            self._fish_round_initial_width = max(
                self._fish_round_initial_width, sample.fill_width
            )
        self._stamina_bar_seen = True
        width = sample.fill_width
        state = sample.midpoint_state
        self._stamina_sample_count += 1
        observed_at = time.monotonic()
        self._last_stamina_seen_at = observed_at
        self._fish_round_last_stamina_at = observed_at
        self._stamina_last_center = sample.center
        self._stamina_midpoint_state = state

        if self._stamina_probe_offset_x is None:
            self._stamina_probe_offset_x = max(1, width // 2)
        elif not self._stamina_low_seen and width > self._stamina_peak_width:
            # 上钩首帧可能刚好处于动画缩放；变灰前允许用更宽的绿条修正半条位置。
            self._stamina_probe_offset_x = max(
                self._stamina_probe_offset_x, width // 2
            )

        previous_peak = self._stamina_peak_width
        if previous_peak == 0:
            self._stamina_peak_width = width
        else:
            self._stamina_peak_width = max(previous_peak, width)
        self._stamina_last_width = width
        # Tolerate fill-width measurement jitter while requiring a near-full refill.
        if (
            self._fish_round_rebounded
            and self._fish_round_initial_width > 0
            and width
            >= self._fish_round_initial_width * self.STAMINA_FULL_RECOVERY_RATIO
        ):
            self._fish_round_full_recovered = True

        if observed_at - self._last_stamina_observation_log_at >= 0.9:
            self._emit(
                EventKind.INFO,
                f"体力条扫描命中：填充 {width} px，位置 {sample.center}，"
                f"中点 {state.value}（绿 {sample.midpoint_green_ratio:.2f} / "
                f"灰 {sample.midpoint_dark_ratio:.2f}），中鱼锚点 OK "
                f"{sample.anchor_confidence:.3f}，第 {self._stamina_sample_count} 次采样。",
                monitoring=True,
            )
            self._last_stamina_observation_log_at = observed_at

        if previous_peak == 0:
            self._emit(
                EventKind.INFO,
                f"体力条首帧：锁定半条采样点 {self._stamina_probe_offset_x} px，"
                "等待该位置连续变灰。",
                monitoring=True,
            )

        if state == StaminaMidpointState.UNKNOWN:
            self._stamina_midpoint_dark_frames = 0
            self._stamina_midpoint_green_frames = 0
            self._stamina_rebound_started = False
            return False

        if not self._stamina_low_seen:
            self._stamina_midpoint_green_frames = 0
            if state == StaminaMidpointState.DARK:
                self._stamina_midpoint_dark_frames += 1
            else:
                self._stamina_midpoint_dark_frames = 0
            if (
                self._stamina_midpoint_dark_frames
                >= self.STAMINA_MIDPOINT_DARK_CONFIRM_FRAMES
            ):
                self._stamina_low_seen = True
                self._fish_round_depleted = True
                self._emit(
                    EventKind.INFO,
                    "体力条中点已连续变灰：确认第一次跌破半条；"
                    "本次不收杆，开始等待中点恢复绿色。",
                    monitoring=True,
                )
            return False

        if state == StaminaMidpointState.GREEN:
            self._stamina_midpoint_green_frames += 1
            if self._stamina_midpoint_green_frames == 1:
                self._stamina_rebound_started = True
                self._emit(
                    EventKind.INFO,
                    "体力条中点开始恢复绿色，正在确认连续帧。",
                    monitoring=True,
                )
            if (
                self._stamina_midpoint_green_frames
                >= self.STAMINA_MIDPOINT_GREEN_CONFIRM_FRAMES
            ):
                self._fish_round_rebounded = True
                self._emit(
                    EventKind.INFO,
                    "体力条中点已连续恢复绿色：确认活鱼反弹，达到收鱼条件。",
                    monitoring=True,
                )
                return True
        else:
            self._stamina_midpoint_green_frames = 0
            self._stamina_rebound_started = False
        return False

    def _finish_uncollected_fishing_round(self) -> None:
        if self._fish_round_full_recovered:
            self._record_fishing_session_result(FishingResult.FAILURE)
        elif not self._fish_round_rebounded:
            self._record_fishing_session_result(FishingResult.ORDINARY)
        else:
            self._emit(
                EventKind.WARNING,
                "检测到体力条回弹，但未能确认重新涨满；本轮暂不计入三类结果，"
                "以免把识别漏帧误报为失败或普通成功。",
                monitoring=True,
            )
        self._fish_resolution_pending = False
        self._waiting_for_clear = False
        self._reset_stamina_tracking()
        self._reset_fishing_round_tracking()

    def _finish_collected_fishing_round(self) -> None:
        if not self._fish_round_had_stamina:
            self._emit(
                EventKind.WARNING,
                "收鱼操作后目标消失，但本轮未确认体力条；"
                "为避免误分类，本轮未计入三类结果。",
                monitoring=True,
            )
        elif self._fish_round_full_recovered:
            self._record_fishing_session_result(FishingResult.FAILURE)
        elif self._fish_round_collect_pressed:
            self._record_fishing_session_result(FishingResult.CATCH)
        elif not self._fish_round_rebounded:
            self._record_fishing_session_result(FishingResult.ORDINARY)
        else:
            self._emit(
                EventKind.WARNING,
                "检测到体力条回弹，但结果证据不完整；本轮暂不计数。",
                monitoring=True,
            )
        self._waiting_for_clear = False
        self._reset_stamina_tracking()
        self._reset_fishing_round_tracking()

    def _metric_message(self, icon_state: IconState, now: float, config: AppConfig) -> str:
        if self._fish_resolution_pending:
            if self._catch_strategy(config) == "fixed_delay":
                elapsed = max(0.0, now - (self._hook_started_at or now))
                wait_seconds, latest_seconds, collect_after = (
                    self.fixed_delay_timing(config)
                )
                return (
                    f"模式 2：已等待 {elapsed:.1f} / {collect_after:.1f} 秒"
                    f"（等待 {wait_seconds:.1f}，最迟 {latest_seconds:.1f}）"
                )
            if self._stamina_peak_width:
                if self._stamina_rebound_started:
                    phase = "中点已回绿，确认连续帧"
                elif self._stamina_low_seen:
                    phase = "中点已变灰，等待反弹回绿"
                else:
                    phase = "等待中点连续变灰"
                return (
                    f"活鱼体力条 {self._stamina_last_width} px / "
                    f"峰值 {self._stamina_peak_width} px · {phase}"
                )
            if config.learned_escape_seconds > 0:
                target, _margin = self.learned_collect_timing(
                    config.learned_escape_seconds
                )
                elapsed = max(0.0, now - (self._hook_started_at or now))
                return f"寻找绿色体力条…计时兜底 {elapsed:.1f} / {target:.1f} 秒"
            return "正在寻找绿色活鱼体力条…"
        return {
            IconState.NORMAL: "正在识别普通图标",
            IconState.READY_TO_CAST: "检测到可抛竿鱼竿图标，准备立即续钓",
            IconState.WAITING_BITE: "已经抛竿，正在等待上钩",
            IconState.FISH_HOOKED: "检测到上钩图标",
            IconState.IDLE_RECOVERY: "检测到指南针状态，准备移动恢复",
            IconState.HORSE_MOUNT_PROMPT: "检测到骑马图标，已阻止自动按键",
            IconState.HORSE_DISMOUNT_PROMPT: "检测到下马图标，正在恢复钓鱼状态",
        }[icon_state]

    def _reset_stamina_tracking(self) -> None:
        self._hook_started_at = None
        self._stamina_peak_width = 0
        self._stamina_last_width = 0
        self._stamina_low_seen = False
        self._stamina_rebound_started = False
        self._stamina_bar_seen = False
        self._stamina_sample_count = 0
        self._last_stamina_observation_log_at = 0.0
        self._last_stamina_seen_at = 0.0
        self._stamina_last_center = None
        self._stamina_probe_offset_x = None
        self._stamina_midpoint_state = StaminaMidpointState.UNKNOWN
        self._stamina_midpoint_dark_frames = 0
        self._stamina_midpoint_green_frames = 0
        self._last_stamina_scan_at = 0.0
