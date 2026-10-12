"""引擎公共入口：集中持有状态、线程、锁和生命周期；具体职责见 automation/ 与 vision/。"""
from __future__ import annotations

import numpy as np
import threading
import time
from fishing_assistant import window_target
from fishing_assistant.automation.capture import CaptureMixin
from fishing_assistant.automation.diagnostics import DiagnosticsMixin
from fishing_assistant.automation.fishing import FishingFlowMixin
from fishing_assistant.automation.input import GameInputMixin
from fishing_assistant.automation.inventory import InventoryCleanupMixin
from fishing_assistant.automation.inventory_entry import InventoryEntryMixin
from fishing_assistant.automation.models import (
    EngineEvent,
    EventCallback,
    EventKind,
    FishingResult,
    IconColorSignals,
    IconState,
    StaminaBarSample,
    StaminaMidpointState,
    _CleanupCancelled,
    _OperationCancelled,
)
from fishing_assistant.automation.monitor import MonitorMixin
from fishing_assistant.automation.pause import PauseControlMixin
from fishing_assistant.automation.recovery import RecoveryMixin
from fishing_assistant.automation.tasks import TaskControlMixin
from fishing_assistant.config import AppConfig, load_config, save_config
from fishing_assistant.diagnostics import record_error
from fishing_assistant.features.fishing_history.store import (
    FishingHistoryRecord,
    FishingHistoryStore,
    FishingHistorySummary,
)
from fishing_assistant.vision.fishing_icons import FishingIconRecognitionMixin
from fishing_assistant.vision.fishing_stamina import FishingStaminaRecognitionMixin
from fishing_assistant.vision.ok_templates import OkTemplateRecognitionMixin
from fishing_assistant.vision.shadow import ShadowRecorder
from ok.feature.FeatureSet import FeatureSet
from pynput import keyboard


class FishingEngine(
    PauseControlMixin,
    TaskControlMixin,
    DiagnosticsMixin,
    FishingIconRecognitionMixin,
    FishingStaminaRecognitionMixin,
    OkTemplateRecognitionMixin,
    MonitorMixin,
    CaptureMixin,
    FishingFlowMixin,
    RecoveryMixin,
    InventoryCleanupMixin,
    InventoryEntryMixin,
    GameInputMixin,
):
    """后台识别服务，可被桌面 UI、命令行或未来的其他界面复用。"""

    ESCAPE_MESSAGE_MATCH_THRESHOLD = 0.68
    ESCAPE_MESSAGE_WATCH_SECONDS = 2.8
    CAST_TRANSITION_GRACE_SECONDS = 1.5
    BACKGROUND_HOVER_REFRESH_DELAY_SECONDS = 0.08
    OK_ICON_MATCH_THRESHOLD = 0.86
    OK_ICON_MATCH_MARGIN = 0.04
    # 游戏窗口尺寸在会话内不变：记住每类模板上次命中的尺度，
    # 下一帧优先尝试；高置信命中后提前结束扫描，压低每帧匹配成本。
    OK_SCALE_HINT_MIN_CONFIDENCE = 0.70
    # 早退只用于纯阈值判定的扫描（文字/锚点）；主图标与旋转指南针靠
    # 「最高分与次高分的差距」判别，早退会把相似模板的分数一起压到
    # 早退线附近、抹掉 margin，因此那两处必须扫完取真实最高分。
    # 窗口尺寸在会话内不变，因此每个模板自己命中过的尺度会重复有效；
    # 但不同模板的正确尺度互不可推（裁剪后的原生尺寸各异），所以只用
    # 「该模板自己的历史命中尺度」限缩扫描，没有历史就扫全范围。
    # 连续未判定时每 N 帧回退一次全范围扫描，兼容用户中途改窗口大小。
    OK_SCALE_LOCK_NEIGHBORS = 3
    OK_SCALE_RESCAN_EVERY = 8
    # 图标 hint 只收「判定级」命中：过渡帧 0.70-0.85 的垃圾命中若能写入
    # hint，会把该模板限缩在错误尺度、分数落入重试死区后永远救不回来。
    OK_ICON_HINT_MIN_CONFIDENCE = OK_ICON_MATCH_THRESHOLD
    # 受限扫描下最高分达到 hint 可记录水位却判定失败时，当帧立刻回退
    # 全范围重扫主模板；此闸必须 ≤ 所有 hint 记录门槛，才不存在死区。
    OK_SCALE_RETRY_MIN_CONFIDENCE = 0.70
    # 上钩期间反弹窗口按 ~60ms 采样节奏设计，主循环睡眠必须跟着缩短。
    PENDING_RESOLUTION_POLL_SECONDS = 0.015
    OK_IDLE_ROTATED_MATCH_THRESHOLD = 0.82
    OK_IDLE_ROTATED_MATCH_MARGIN = 0.025
    # 实机 WGC 画面中的指南针会因缩放与背景导致整图分数降到约 0.45～0.55。
    # 只有整图先成为候选，再由旋转不变的中心黑点锚点复核，避免误认其他圆形按钮。
    OK_IDLE_CORRECTED_MATCH_THRESHOLD = 0.42
    OK_IDLE_CORRECTED_MATCH_MARGIN = 0.06
    OK_IDLE_CENTER_MATCH_THRESHOLD = 0.74
    OK_ICON_NORMALIZED_WIDTH = 160
    COMPASS_PIXEL_MATCH_THRESHOLD = 0.50
    MONITOR_RETRY_MAX_DELAY_SECONDS = 2.0
    STAMINA_ANCHOR_MATCH_THRESHOLD = 0.80
    STAMINA_LOST_GRACE_SECONDS = 0.75
    STAMINA_MIDPOINT_GREEN_RATIO = 0.45
    STAMINA_MIDPOINT_DARK_RATIO = 0.55
    STAMINA_MIDPOINT_DARK_CONFIRM_FRAMES = 2
    STAMINA_MIDPOINT_GREEN_CONFIRM_FRAMES = 2
    STAMINA_FULL_RECOVERY_RATIO = 0.9
    STARTUP_IDLE_CONFIRM_FRAMES = 2
    ROD_REQUIRED_MATCH_THRESHOLD = 0.72
    INVENTORY_FULL_MATCH_THRESHOLD = 0.70
    INVENTORY_FULL_ICON_MATCH_THRESHOLD = 0.82
    BLOCKING_MESSAGE_RETRY_THRESHOLD = 3
    BLOCKING_MESSAGE_CONFIRM_FRAMES = 2
    BLOCKING_MESSAGE_SCAN_INTERVAL_SECONDS = 0.16
    CLEANUP_SCREEN_TIMEOUT_SECONDS = 8.0
    CLEANUP_CONFIRM_FRAMES = 3
    CLEANUP_CONFIRM_INTERVAL_SECONDS = 0.14
    _escape_template_mask: np.ndarray | None = None
    _rod_required_template_mask: np.ndarray | None = None
    _inventory_full_template_mask: np.ndarray | None = None
    _inventory_full_icon_template: np.ndarray | None = None
    _ok_feature_set: FeatureSet | None = None
    _ok_icon_templates: dict[str, np.ndarray] | None = None
    _ok_idle_rotated_templates: tuple[np.ndarray, ...] | None = None
    _ok_idle_center_template: np.ndarray | None = None
    _stamina_anchor_template: np.ndarray | None = None
    _scale_hints: dict[str, float] = {}
    _no_decision_streak = 0
    _last_decided_state: IconState | None = None

    def __init__(
        self,
        event_callback: EventCallback | None = None,
        history_store: FishingHistoryStore | None = None,
    ) -> None:
        self._config = load_config()
        self._config_lock = threading.RLock()
        self._event_callback = event_callback
        self._fishing_history = history_store or FishingHistoryStore()
        self._fishing_history_id: int | None = None
        self._enabled = threading.Event()
        self._paused = threading.Event()
        self._craft_session_lock = threading.RLock()
        self._paused_at = 0.0
        self._cleanup_in_progress = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None
        self._listener: keyboard.Listener | None = None
        self._hotkeys_down: set[keyboard.Key] = set()
        self._work_context = threading.local()
        self._debug_capture_lock = threading.Lock()
        self._debug_capture_thread: threading.Thread | None = None
        self._cleanup_test_requested = threading.Event()
        self._craft_request = None
        self._ignore_esc_until = 0.0

        self._waiting_for_clear = False
        self._red_frames = 0
        self._clear_frames = 0
        self._idle_frames = 0
        self._interrupt_generation = 0
        self._pending_recast_at: float | None = None
        self._pending_recast_reason = ""
        self._refresh_hover_before_recast = False
        self._startup_probe_active = False
        # 连续未识别自动取证：起点时间戳 / 上次落盘时间 / 本次会话已落份数。
        self._unrecognized_since: float | None = None
        self._last_diag_snapshot_at: float | None = None
        self._diag_snapshot_count = 0
        self._last_press_at = 0.0
        self._last_recovery_at = 0.0
        self._last_metric_at = 0.0
        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state: IconState | None = None
        self._horse_dismount_attempted = False
        self._last_horse_dismount_at = 0.0
        self._horse_settle_until = 0.0
        self._ok_window_backend: window_target.OkWindowBackend | None = None
        self._backend_lock = threading.RLock()
        self._shadow_recorder: ShadowRecorder | None = None
        self._shadow_prev_icon: IconState | None = None
        self._fish_resolution_pending = False
        self._hook_started_at: float | None = None
        self._fishing_session_id = 0
        self._successful_fishing_count = 0
        self._ordinary_fishing_count = 0
        self._failed_fishing_count = 0
        self._fishing_session_active = False
        self._fish_round_had_stamina = False
        self._fish_round_depleted = False
        self._fish_round_rebounded = False
        self._fish_round_full_recovered = False
        self._fish_round_initial_width = 0
        self._fish_round_collect_pressed = False
        self._fish_round_last_stamina_at = 0.0
        self._stamina_peak_width = 0
        self._stamina_last_width = 0
        self._stamina_low_seen = False
        self._stamina_rebound_started = False
        self._stamina_bar_seen = False
        self._stamina_sample_count = 0
        self._last_stamina_observation_log_at = 0.0
        self._last_stamina_seen_at = 0.0
        self._stamina_last_center: tuple[int, int] | None = None
        self._stamina_probe_offset_x: int | None = None
        self._stamina_midpoint_state = StaminaMidpointState.UNKNOWN
        self._stamina_midpoint_dark_frames = 0
        self._stamina_midpoint_green_frames = 0

        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        self._escape_message_latched = False
        self._last_escape_scan_at = 0.0
        self._unconfirmed_cast_attempts = 0
        self._recovery_attempts_without_success = 0
        self._rod_required_hits = 0
        self._inventory_full_hits = 0
        self._blocking_message_scan_announced = False
        self._last_blocking_message_scan_at = 0.0
        self._last_blocking_message_warning_at = 0.0
        self._last_stamina_scan_at = 0.0
        self._last_stamina_warning_at = 0.0
        self._last_stamina_missing_log_at = 0.0
        self._last_logged_icon_state: IconState | None = None
        self._last_logged_recognition_source = ""
        self._last_background_hover_at = 0.0

    def set_event_callback(self, callback: EventCallback | None) -> None:
        self._event_callback = callback

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._monitor_loop, name="fishing-monitor", daemon=True
        )
        self._thread.start()
        self._listener = keyboard.Listener(
            on_press=self._on_key_press, on_release=self._on_key_release
        )
        self._listener.start()
        self._emit(
            EventKind.INFO,
            "助手已就绪：将鼠标停在钓鱼按钮中心后按 F7 即刻校准（不会移动鼠标）；F8 开始/暂停，F9 保存识别区域和诊断。",
        )

    def close(self) -> None:
        self._interrupt_generation += 1
        self._enabled.clear()
        self._finish_fishing_session("application_closed")
        self._shutdown.set()
        if self._listener is not None:
            self._listener.stop()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._close_ok_window_backend()
        if self._shadow_recorder is not None:
            self._shadow_recorder.close()
        self._fishing_history.close()

    def config(self) -> AppConfig:
        with self._config_lock:
            return self._config.copy()

    def fishing_history_sessions(self, limit: int = 100) -> list[FishingHistoryRecord]:
        return self._fishing_history.list_sessions(limit)

    def fishing_history_summary(self) -> FishingHistorySummary:
        return self._fishing_history.summary()

    def update_config(self, **changes: object) -> AppConfig:
        with self._config_lock:
            self._config = self._config.copy(**changes)
            save_config(self._config)
            config = self._config.copy()
        return config

    _UNRECOGNIZED_SNAPSHOT_AFTER_S = 20.0

    _UNRECOGNIZED_SNAPSHOT_COOLDOWN_S = 60.0

    _UNRECOGNIZED_SNAPSHOT_MAX = 3

    OK_ICON_FULL_SCALES = np.linspace(0.78, 1.28, 11)

    def _on_key_press(
        self, key: keyboard.Key | keyboard.KeyCode | None
    ) -> bool | None:
        # 回调里逃逸的异常会杀死 pynput 监听线程，之后所有快捷键
        # （包括 Esc 紧急停止）都会静默失效，因此必须整体防护。
        try:
            if key in (keyboard.Key.f7, keyboard.Key.f8, keyboard.Key.f9):
                if key in self._hotkeys_down:
                    return None
                self._hotkeys_down.add(key)
            if key == keyboard.Key.f7:
                self.calibrate_from_cursor()
            elif key == keyboard.Key.f8:
                self.toggle_monitoring()
            elif key == keyboard.Key.f9:
                self.request_debug_capture()
            elif key == keyboard.Key.esc:
                # 暂停后 Esc 属于游戏操作，不再重复暂停或播报紧急停止。
                if not self.is_monitoring():
                    return None
                if time.monotonic() < self._ignore_esc_until:
                    return None
                self.set_monitoring(False)
                self._emit(EventKind.WARNING, "已触发紧急停止。")
        except Exception as error:
            record_error("hotkey handler", error)
            self._emit(EventKind.WARNING, f"快捷键处理出现异常：{error}")
        return None

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        self._hotkeys_down.discard(key)

    def _operation_active(self, generation: int) -> bool:
        return (
            self._enabled.is_set()
            and not self._paused.is_set()
            and not self._shutdown.is_set()
            and generation == self._interrupt_generation
        )

    def _ensure_operation_active(self) -> None:
        # 线程局部代数不会被另一个线程的停止/重启覆盖；覆盖到真正送键前。
        generation = getattr(self._work_context, "generation", None)
        if generation is not None and not self._operation_active(generation):
            raise _OperationCancelled()

    def _reset_detection(self) -> None:
        self._waiting_for_clear = False
        self._red_frames = 0
        self._clear_frames = 0
        self._idle_frames = 0
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._refresh_hover_before_recast = False
        self._startup_probe_active = False
        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state = None
        self._horse_dismount_attempted = False
        self._horse_settle_until = 0.0
        self._fish_resolution_pending = False
        self._last_logged_icon_state = None
        self._last_logged_recognition_source = ""
        self._last_stamina_missing_log_at = 0.0
        self._last_background_hover_at = 0.0
        self._clear_failed_start_tracking()
        self._last_blocking_message_warning_at = 0.0
        self._clear_escape_watch()
        self._reset_stamina_tracking()

    def _emit(
        self,
        kind: EventKind,
        message: str,
        **details: object,
    ) -> None:
        details.setdefault("monitoring", self._enabled.is_set())
        if kind == EventKind.ERROR:
            record_error("fishing engine", message)
        if self._event_callback is not None:
            self._event_callback(EngineEvent(kind=kind, message=message, **details))
