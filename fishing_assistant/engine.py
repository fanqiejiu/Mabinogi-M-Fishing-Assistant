"""不依赖 UI 的屏幕识别和全局快捷键服务。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable

import cv2
import mss
import numpy as np
import pyautogui
from pynput import keyboard
from ok.feature.FeatureSet import FeatureSet

from . import window_target

from .config import (
    DEBUG_IMAGE_PATH,
    AppConfig,
    effective_roi_size,
    load_config,
    save_config,
)
from .constants import (
    FISH_ESCAPE_TEMPLATE_PATH,
    INVENTORY_FULL_ICON_TEMPLATE_PATH,
    INVENTORY_FULL_TEMPLATE_PATH,
    OK_ICON_TEMPLATE_PATHS,
    OK_IDLE_MOTION_TEMPLATE_PATH,
    OK_STAMINA_ANCHOR_TEMPLATE_PATH,
    ROD_REQUIRED_TEMPLATE_PATH,
)
from .diagnostics import record_error


class EventKind(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    METRIC = "metric"
    CONFIG = "config"
    STATE = "state"


class IconState(str, Enum):
    NORMAL = "normal"
    READY_TO_CAST = "ready_to_cast"
    WAITING_BITE = "waiting_bite"
    FISH_HOOKED = "fish_hooked"
    IDLE_RECOVERY = "idle_recovery"
    HORSE_MOUNT_PROMPT = "horse_mount_prompt"
    HORSE_DISMOUNT_PROMPT = "horse_dismount_prompt"


class StaminaMidpointState(str, Enum):
    """体力槽半条位置采样块的颜色状态。"""

    UNKNOWN = "unknown"
    GREEN = "green"
    DARK = "dark"


@dataclass(frozen=True, slots=True)
class IconColorSignals:
    red_pixels: int
    red_ratio: float
    white_ratio: float
    green_ratio: float
    blue_ratio: float
    brown_ratio: float
    recognition_source: str = "compat_pixel"
    recognition_confidence: float = 0.0


@dataclass(frozen=True, slots=True)
class StaminaBarSample:
    """动态体力条的一次观测，并记录半条位置的局部颜色。"""

    fill_width: int
    center: tuple[int, int]
    anchor_confidence: float = 1.0
    fill_left: int | None = None
    fill_height: int = 0
    midpoint_state: StaminaMidpointState = StaminaMidpointState.UNKNOWN
    midpoint_green_ratio: float = 0.0
    midpoint_dark_ratio: float = 0.0


@dataclass(slots=True)
class EngineEvent:
    kind: EventKind
    message: str
    red_pixels: int = 0
    recognition_source: str = ""
    recognition_confidence: float = 0.0
    fish_visible: bool = False
    monitoring: bool = False
    icon_state: IconState = IconState.NORMAL
    debug_image: Path | None = None
    stamina_fill_width: int = 0
    stamina_peak_width: int = 0
    waiting_for_bounce: bool = False
    catch_strategy: str = ""
    hook_elapsed_seconds: float = 0.0


EventCallback = Callable[[EngineEvent], None]


class FishingEngine:
    """后台识别服务，可被桌面 UI、命令行或未来的其他界面复用。"""

    ESCAPE_MESSAGE_MATCH_THRESHOLD = 0.68
    ESCAPE_MESSAGE_WATCH_SECONDS = 2.8
    CAST_TRANSITION_GRACE_SECONDS = 1.5
    BACKGROUND_HOVER_REFRESH_DELAY_SECONDS = 0.08
    OK_ICON_MATCH_THRESHOLD = 0.86
    OK_ICON_MATCH_MARGIN = 0.04
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
    STARTUP_IDLE_CONFIRM_FRAMES = 2
    ROD_REQUIRED_MATCH_THRESHOLD = 0.72
    INVENTORY_FULL_MATCH_THRESHOLD = 0.70
    INVENTORY_FULL_ICON_MATCH_THRESHOLD = 0.82
    BLOCKING_MESSAGE_RETRY_THRESHOLD = 3
    BLOCKING_MESSAGE_CONFIRM_FRAMES = 2
    BLOCKING_MESSAGE_SCAN_INTERVAL_SECONDS = 0.16
    _escape_template_mask: np.ndarray | None = None
    _rod_required_template_mask: np.ndarray | None = None
    _inventory_full_template_mask: np.ndarray | None = None
    _inventory_full_icon_template: np.ndarray | None = None
    _ok_feature_set: FeatureSet | None = None
    _ok_icon_templates: dict[str, np.ndarray] | None = None
    _ok_idle_rotated_templates: tuple[np.ndarray, ...] | None = None
    _ok_idle_center_template: np.ndarray | None = None
    _stamina_anchor_template: np.ndarray | None = None

    def __init__(self, event_callback: EventCallback | None = None) -> None:
        self._config = load_config()
        self._config_lock = threading.RLock()
        self._event_callback = event_callback
        self._enabled = threading.Event()
        self._shutdown = threading.Event()
        self._thread: threading.Thread | None = None
        self._listener: keyboard.Listener | None = None

        self._waiting_for_clear = False
        self._red_frames = 0
        self._clear_frames = 0
        self._idle_frames = 0
        self._pending_recast_at: float | None = None
        self._pending_recast_reason = ""
        self._refresh_hover_before_recast = False
        self._startup_probe_active = False
        self._last_press_at = 0.0
        self._last_recovery_at = 0.0
        self._last_metric_at = 0.0
        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state: IconState | None = None
        self._last_horse_dismount_at = 0.0
        self._horse_settle_until = 0.0
        self._ok_window_backend: window_target.OkWindowBackend | None = None
        self._fish_resolution_pending = False
        self._hook_started_at: float | None = None
        self._stamina_peak_width = 0
        self._stamina_trough_width = 0
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
        self._listener = keyboard.Listener(on_press=self._on_key_press)
        self._listener.start()
        self._emit(
            EventKind.INFO,
            "助手已就绪：将鼠标停在钓鱼按钮中心后按 F7 即刻校准（不会移动鼠标）；F8 开始/暂停，F9 保存识别区域。",
        )

    def close(self) -> None:
        self._enabled.clear()
        self._shutdown.set()
        if self._listener is not None:
            self._listener.stop()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
        self._close_ok_window_backend()

    def config(self) -> AppConfig:
        with self._config_lock:
            return self._config.copy()

    def update_config(self, **changes: object) -> AppConfig:
        with self._config_lock:
            self._config = self._config.copy(**changes)
            save_config(self._config)
            config = self._config.copy()
        return config

    def calibrate_from_cursor(self) -> tuple[int, int]:
        x, y = pyautogui.position()
        config = self.config()
        if config.capture_mode == "window":
            try:
                target = self._resolve_target_window(config)
            except RuntimeError as error:
                self._emit(EventKind.WARNING, f"后台模式校准失败：{error}")
                return x, y
            if not target.contains(x, y):
                self._emit(
                    EventKind.WARNING,
                    "鼠标不在选定的目标窗口内，请先切到目标窗口再校准。",
                )
                return x, y
            offset = (x - target.left, y - target.top)
            self.update_config(
                button_center=(x, y),
                target_window_handle=target.handle,
                target_window_title=target.title,
                target_button_offset=offset,
            )
            message = (
                f"F7 已校准目标窗口“{target.title}”内按钮：({offset[0]}, {offset[1]})；"
                "已直接记录，鼠标位置未移动。"
            )
        else:
            self.update_config(button_center=(x, y))
            message = f"F7 已校准钓鱼按钮中心：({x}, {y})；已直接记录，鼠标位置未移动。"
        self._reset_detection()
        if self._enabled.is_set():
            self._startup_probe_active = True
            self._schedule_recast(
                time.monotonic(), self.config(), "重新校准完成"
            )
        self._emit(EventKind.SUCCESS, message)
        return x, y
    def set_monitoring(self, enabled: bool) -> bool:
        config = self.config()
        if enabled:
            if config.capture_mode == "window":
                if config.target_button_offset is None:
                    self._emit(EventKind.WARNING, "请先选择目标窗口并在窗口内完成校准。")
                    return False
                try:
                    self._resolve_target_window(config)
                except RuntimeError as error:
                    self._emit(EventKind.WARNING, f"无法启动后台模式：{error}")
                    return False
            elif config.button_center is None:
                self._emit(EventKind.WARNING, "请先把鼠标停在圆形按钮中心后按 F7 校准。")
                return False
        self._reset_detection()
        if enabled:
            self._startup_probe_active = True
            self._prepare_stamina_view(config)
            if config.capture_mode == "window":
                target = self._resolve_target_window(config)
                self._maintain_background_hover(target, config, force=True)
                self._emit(
                    EventKind.INFO,
                    f"后台虚拟悬停已锁定至窗口内 {config.target_button_offset}；真实鼠标可自由移动。",
                    monitoring=True,
                )
            self._enabled.set()
            self._schedule_recast(time.monotonic(), config, "监测启动")
            self._emit(EventKind.INFO, self._monitoring_details(config), monitoring=True)
            if config.capture_mode == "window" and config.window_backend == "ok":
                self._emit(EventKind.INFO, "OK WGC 正在预热首帧，首次启动会在画面到达后自动开始识别。", monitoring=True)
            message = (
                "OK 指定窗口模式已启动；临时错误会按设置重试，达到上限后暂停。"
                if config.capture_mode == "window"
                else "监测已启动，请把游戏保持在前台。"
            )
            self._emit(EventKind.STATE, message, monitoring=True)
        else:
            self._enabled.clear()
            self._emit(EventKind.STATE, "监测已暂停，不会发送按键。", monitoring=False)
        return True
    def toggle_monitoring(self) -> None:
        self.set_monitoring(not self._enabled.is_set())

    def is_monitoring(self) -> bool:
        return self._enabled.is_set()

    def save_debug_capture(self) -> Path | None:
        config = self.config()
        if config.capture_mode == "window":
            missing_calibration = config.target_button_offset is None
        else:
            missing_calibration = config.button_center is None
        if missing_calibration:
            self._emit(EventKind.WARNING, "请先完成校准，才能保存识别区域。")
            return None
        try:
            if config.capture_mode == "window":
                frame = self._capture_frame(None, config)
            else:
                with mss.MSS() as screen:
                    frame = self._capture_frame(screen, config)
            cv2.imwrite(str(DEBUG_IMAGE_PATH), frame[:, :, :3])
        except Exception as error:  # pragma: no cover - 依赖实际显示器状态
            self._emit(EventKind.ERROR, f"保存识别区域失败：{error}")
            return None
        self._emit(
            EventKind.SUCCESS,
            "识别区域快照已保存，可用它确认圆形按钮是否完整包含。",
            debug_image=DEBUG_IMAGE_PATH,
        )
        return DEBUG_IMAGE_PATH

    @staticmethod
    def _icon_circle_mask(height: int, width: int) -> np.ndarray:
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.ellipse(
            mask,
            (width // 2, height // 2),
            (int(width * 0.46), int(height * 0.43)),
            0,
            0,
            360,
            255,
            -1,
        )
        return mask

    @classmethod
    def analyze_icon_colors(cls, bgr: np.ndarray) -> IconColorSignals:
        """统计圆形按钮内的红、白、绿、棕比例，用于钓鱼和骑马图标识别。"""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        low_red = cv2.inRange(
            hsv, np.array([0, 105, 95]), np.array([15, 255, 255])
        )
        high_red = cv2.inRange(
            hsv, np.array([165, 105, 95]), np.array([179, 255, 255])
        )
        red_mask = cv2.bitwise_or(low_red, high_red)
        white_mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([179, 55, 255]))
        green_mask = cv2.inRange(hsv, np.array([35, 55, 80]), np.array([95, 255, 255]))
        blue_mask = cv2.inRange(hsv, np.array([88, 60, 70]), np.array([132, 255, 255]))
        brown_mask = cv2.inRange(hsv, np.array([5, 65, 60]), np.array([28, 255, 255]))
        circle_mask = cls._icon_circle_mask(*red_mask.shape)
        area = max(1, int(cv2.countNonZero(circle_mask)))

        def ratio(mask: np.ndarray) -> float:
            return cv2.countNonZero(cv2.bitwise_and(mask, circle_mask)) / area

        red_ratio = ratio(red_mask)
        return IconColorSignals(
            red_pixels=int(round(red_ratio * area)),
            red_ratio=red_ratio,
            white_ratio=ratio(white_mask),
            green_ratio=ratio(green_mask),
            blue_ratio=ratio(blue_mask),
            brown_ratio=ratio(brown_mask),
        )

    @classmethod
    def compass_pixel_confidence(cls, bgr: np.ndarray) -> float:
        """在按钮中心附近搜索旋转不变的黑色圆点，并以指针配色复核。"""
        if bgr.ndim != 3 or bgr.shape[0] < 20 or bgr.shape[1] < 20:
            return 0.0
        cropped = cls._crop_ok_icon_image(bgr[:, :, :3])
        normalized = cv2.resize(cropped, (128, 128), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(normalized, cv2.COLOR_BGR2HSV)
        hue, saturation, value = cv2.split(hsv)

        black_mask = (value <= 45).astype(np.uint8)
        count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
            black_mask, 8
        )
        best_dot_area = 0
        for component in range(1, count):
            x, y, width, height, area = (
                int(item) for item in stats[component, :5]
            )
            center_x, center_y = (float(item) for item in centroids[component])
            fill_ratio = area / max(1, width * height)
            aspect_ratio = width / max(1, height)
            if (
                35 <= center_x <= 93
                and 35 <= center_y <= 93
                and 60 <= area <= 320
                and 8 <= width <= 26
                and 8 <= height <= 26
                and 0.50 <= fill_ratio <= 1.0
                and 0.55 <= aspect_ratio <= 1.80
            ):
                best_dot_area = max(best_dot_area, area)

        red_ratio = float(
            (
                ((hue <= 12) | (hue >= 170))
                & (saturation >= 90)
                & (value >= 90)
            ).mean()
        )
        white_ratio = float(((saturation <= 45) & (value >= 180)).mean())
        green_ratio = float(
            (
                (hue >= 35)
                & (hue <= 100)
                & (saturation >= 55)
                & (value >= 70)
            ).mean()
        )
        dot_confidence = min(1.0, best_dot_area / 120)
        if (
            dot_confidence >= cls.COMPASS_PIXEL_MATCH_THRESHOLD
            and 0.008 <= red_ratio <= 0.045
            and 0.035 <= white_ratio <= 0.16
            and 0.15 <= green_ratio <= 0.52
        ):
            return dot_confidence
        return 0.0

    @classmethod
    def count_fish_red_pixels(cls, bgr: np.ndarray) -> int:
        """兼容既有调用：只返回圆形按钮内的红橙色像素数。"""
        return cls.analyze_icon_colors(bgr).red_pixels

    @staticmethod
    def classify_icon_state(red_pixels: int, config: AppConfig) -> IconState:
        """区分上钩鱼体、原地失效指针和普通抛竿/等待图标。"""
        if red_pixels >= config.fish_red_pixel_threshold:
            return IconState.FISH_HOOKED
        if config.idle_red_pixel_min <= red_pixels <= config.idle_red_pixel_max:
            return IconState.IDLE_RECOVERY
        if config.idle_red_pixel_max < red_pixels < config.fish_red_pixel_threshold:
            return IconState.READY_TO_CAST
        return IconState.NORMAL

    @classmethod
    def classify_frame_state(
        cls, bgr: np.ndarray, config: AppConfig
    ) -> tuple[IconState, IconColorSignals]:
        """运行所选识别后端；OK 模式仅对旋转指南针使用专用像素校正。"""
        if config.recognition_backend != "pixel":
            # 指南针会持续旋转，先用中心黑点与固定配色判定；其他图标仍交给 OK。
            signals = IconColorSignals(0, 0.0, 0.0, 0.0, 0.0, 0.0)
            compass_confidence = cls.compass_pixel_confidence(bgr)
            if compass_confidence:
                return IconState.IDLE_RECOVERY, replace(
                    signals,
                    recognition_source="compass_pixel",
                    recognition_confidence=compass_confidence,
                )
            try:
                state, best_confidence, _second_confidence = (
                    cls.ok_icon_state_match(bgr)
                )
            except Exception:
                state, best_confidence = None, 0.0
            return state or IconState.NORMAL, replace(
                signals,
                recognition_source="ok_feature",
                recognition_confidence=best_confidence,
            )

        signals = cls.analyze_icon_colors(bgr)
        is_horse_icon = (
            signals.white_ratio >= 0.10
            and signals.green_ratio >= 0.38
            and 0.01 <= signals.brown_ratio <= 0.035
        )
        if is_horse_icon:
            state = (
                IconState.HORSE_DISMOUNT_PROMPT
                if signals.red_ratio >= 0.015
                else IconState.HORSE_MOUNT_PROMPT
            )
            return state, signals
        is_ready_rod = (
            signals.blue_ratio >= 0.14
            and signals.brown_ratio >= 0.015
            and signals.red_ratio < 0.085
        )
        if is_ready_rod:
            return IconState.READY_TO_CAST, signals

        state = cls.classify_icon_state(signals.red_pixels, config)
        if (
            state == IconState.NORMAL
            and signals.white_ratio >= 0.12
            and signals.green_ratio >= 0.45
            and signals.brown_ratio < 0.01
        ):
            state = IconState.WAITING_BITE
        return state, signals

    @classmethod
    def _load_stamina_anchor_template(cls) -> np.ndarray | None:
        if cls._stamina_anchor_template is None:
            cls._stamina_anchor_template = cv2.imread(
                str(OK_STAMINA_ANCHOR_TEMPLATE_PATH), cv2.IMREAD_COLOR
            )
        return cls._stamina_anchor_template

    @classmethod
    def _stamina_anchor_confidence(
        cls,
        bgr: np.ndarray,
        x: int,
        y: int,
        width: int,
        height: int,
    ) -> float:
        """在绿条上方用 OK 彩色特征确认随角色移动的中鱼圆形图标。"""
        template = cls._load_stamina_anchor_template()
        if template is None:
            return 0.0
        frame_height, frame_width = bgr.shape[:2]
        horizontal_span = max(140, min(420, width * 4))
        vertical_span = max(80, min(240, height * 8))
        left = max(0, x - round(horizontal_span * 0.25))
        right = min(frame_width, x + horizontal_span)
        top = max(0, y - vertical_span)
        bottom = min(frame_height, y + max(2, height // 3))
        if right - left < 20 or bottom - top < 20:
            return 0.0
        search = bgr[top:bottom, left:right, :3]
        return cls._ok_multiscale_confidence(
            search,
            template,
            search_top_ratio=0.0,
            search_bottom_ratio=1.0,
            scales=np.array(
                [0.65, 0.75, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20, 1.35, 1.55]
            ),
            normalized_width=search.shape[1],
            baseline_scale=1.0,
            category_name="stamina_fish_anchor",
            use_gray_scale=False,
        )

    @classmethod
    def find_stamina_bar(
        cls,
        bgr: np.ndarray,
        *,
        require_anchor: bool = False,
        preferred_center: tuple[int, int] | None = None,
    ) -> StaminaBarSample | None:
        """全画面寻找绿条；实机模式再用其上方的中鱼图标作 OK 锚点确认。"""
        if bgr.ndim != 3 or bgr.shape[0] <= 0 or bgr.shape[1] <= 0:
            return None
        hsv = cv2.cvtColor(bgr[:, :, :3], cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(
            hsv, np.array([35, 60, 70]), np.array([100, 255, 255])
        )
        green_mask = cv2.morphologyEx(
            green_mask, cv2.MORPH_OPEN, np.ones((2, 2), dtype=np.uint8)
        )
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
            green_mask, connectivity=8
        )
        # 绿条会跟随角色在整张画面中移动。先按细长填充和深色槽体找候选，
        # 再用候选上方的中鱼圆形图标做 OK 特征确认，不锁定屏幕坐标。
        dark_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([179, 255, 90]))
        frame_height, frame_width = bgr.shape[:2]
        candidates: list[tuple[StaminaBarSample, float, bool]] = []
        for index in range(1, count):
            x, y, width, height, area = (int(value) for value in stats[index])
            if not (24 <= width <= 480 and 5 <= height <= 32):
                continue
            if width < height * 2 or area < width * height * 0.55:
                continue
            # 绿色填充右边应当是尚未消耗的深色进度槽。用条内中段避免圆角和描边干扰。
            core_top = y + max(1, height // 4)
            core_bottom = min(frame_height, y + height - max(1, height // 4))
            track_depth = min(240, max(24, width * 2))
            right = min(frame_width, x + width + track_depth)
            right_band = dark_mask[core_top:core_bottom, x + width : right]
            right_dark_ratio = (
                float(cv2.countNonZero(right_band)) / max(1, right_band.size)
            )
            # 满体力时右侧空槽很短，因此保留上下深色描边作为弱结构特征。
            border_top = dark_mask[max(0, y - 3) : y, x : x + width]
            border_bottom = dark_mask[
                y + height : min(frame_height, y + height + 3), x : x + width
            ]
            border_size = border_top.size + border_bottom.size
            border_dark_ratio = (
                float(cv2.countNonZero(border_top) + cv2.countNonZero(border_bottom))
                / max(1, border_size)
            )
            track_score = right_dark_ratio * 2.0 + border_dark_ratio * 0.35
            anchor_confidence = (
                cls._stamina_anchor_confidence(bgr, x, y, width, height)
                if require_anchor
                else 1.0
            )
            if (
                require_anchor
                and anchor_confidence < cls.STAMINA_ANCHOR_MATCH_THRESHOLD
            ):
                continue
            sample = StaminaBarSample(
                width,
                (x + width // 2, y + height // 2),
                anchor_confidence,
                fill_left=x,
                fill_height=height,
            )
            in_focus_area = (
                frame_width * 0.20 <= sample.center[0] <= frame_width * 0.80
                and frame_height * 0.10 <= sample.center[1] <= frame_height * 0.65
            )
            candidates.append((sample, track_score, in_focus_area))
        if not candidates:
            return None
        # OK 锚点优先；中部位置和填充宽度只在相似度接近时作弱排序。
        sample, _track_score, _in_focus = max(
            candidates,
            key=lambda item: (
                item[0].anchor_confidence,
                (
                    -float(
                        np.hypot(
                            item[0].center[0] - preferred_center[0],
                            item[0].center[1] - preferred_center[1],
                        )
                    )
                    if preferred_center is not None
                    else item[1]
                ),
                item[1],
                0.10 if item[2] else 0.0,
                item[0].fill_width,
            ),
        )
        return sample

    @classmethod
    def classify_stamina_midpoint(
        cls,
        bgr: np.ndarray,
        sample: StaminaBarSample,
        probe_offset_x: int,
    ) -> StaminaBarSample:
        """读取进度槽半条位置的小块颜色，避免用整段绿条宽度猜反弹。"""
        if bgr.ndim != 3 or bgr.shape[0] <= 0 or bgr.shape[1] <= 0:
            return sample
        left = (
            sample.fill_left
            if sample.fill_left is not None
            else sample.center[0] - sample.fill_width // 2
        )
        probe_x = left + max(1, int(probe_offset_x))
        probe_y = sample.center[1]
        radius = max(2, min(6, round(max(7, sample.fill_height) * 0.22)))
        frame_height, frame_width = bgr.shape[:2]
        left_edge = max(0, probe_x - radius)
        right_edge = min(frame_width, probe_x + radius + 1)
        top_edge = max(0, probe_y - radius)
        bottom_edge = min(frame_height, probe_y + radius + 1)
        if right_edge <= left_edge or bottom_edge <= top_edge:
            return sample

        probe = bgr[top_edge:bottom_edge, left_edge:right_edge, :3]
        hsv = cv2.cvtColor(probe, cv2.COLOR_BGR2HSV)
        green_mask = cv2.inRange(
            hsv, np.array([35, 60, 70]), np.array([100, 255, 255])
        )
        dark_mask = cv2.inRange(
            hsv, np.array([0, 0, 0]), np.array([179, 255, 110])
        )
        area = max(1, green_mask.size)
        green_ratio = float(cv2.countNonZero(green_mask)) / area
        dark_ratio = float(cv2.countNonZero(dark_mask)) / area
        if green_ratio >= cls.STAMINA_MIDPOINT_GREEN_RATIO:
            state = StaminaMidpointState.GREEN
        elif dark_ratio >= cls.STAMINA_MIDPOINT_DARK_RATIO:
            state = StaminaMidpointState.DARK
        else:
            state = StaminaMidpointState.UNKNOWN
        return replace(
            sample,
            midpoint_state=state,
            midpoint_green_ratio=green_ratio,
            midpoint_dark_ratio=dark_ratio,
        )

    @staticmethod
    def _white_text_mask(bgr: np.ndarray) -> np.ndarray:
        """提取游戏提示中的低饱和高亮文字，忽略动态场景颜色。"""
        hsv = cv2.cvtColor(bgr[:, :, :3], cv2.COLOR_BGR2HSV)
        return cv2.inRange(
            hsv, np.array([0, 0, 180]), np.array([179, 105, 255])
        )

    @classmethod
    def _load_text_template(cls, path: Path) -> np.ndarray | None:
        template = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if template is None:
            return None
        # 颜色仅用于从静态素材中裁出文字；运行时识别交给 OK FeatureSet。
        mask = cls._white_text_mask(template)
        points = cv2.findNonZero(mask)
        if points is None:
            return None
        x, y, width, height = cv2.boundingRect(points)
        padding = 8
        left = max(0, x - padding)
        top = max(0, y - padding)
        right = min(template.shape[1], x + width + padding)
        bottom = min(template.shape[0], y + height + padding)
        return template[top:bottom, left:right, :3]

    @classmethod
    def _load_escape_template_mask(cls) -> np.ndarray | None:
        if cls._escape_template_mask is None:
            cls._escape_template_mask = cls._load_text_template(
                FISH_ESCAPE_TEMPLATE_PATH
            )
        return cls._escape_template_mask

    @classmethod
    def _load_rod_required_template_mask(cls) -> np.ndarray | None:
        if cls._rod_required_template_mask is None:
            cls._rod_required_template_mask = cls._load_text_template(
                ROD_REQUIRED_TEMPLATE_PATH
            )
        return cls._rod_required_template_mask

    @classmethod
    def _load_inventory_full_template_mask(cls) -> np.ndarray | None:
        if cls._inventory_full_template_mask is None:
            cls._inventory_full_template_mask = cls._load_text_template(
                INVENTORY_FULL_TEMPLATE_PATH
            )
        return cls._inventory_full_template_mask

    @classmethod
    def _get_ok_feature_set(cls) -> FeatureSet:
        if cls._ok_feature_set is None:
            cls._ok_feature_set = FeatureSet(
                False,
                "__direct_templates__.json",
                default_horizontal_variance=0,
                default_vertical_variance=0,
                default_threshold=0.80,
            )
        return cls._ok_feature_set

    @classmethod
    def _ok_multiscale_confidence(
        cls,
        bgr: np.ndarray,
        template: np.ndarray | None,
        *,
        search_top_ratio: float,
        search_bottom_ratio: float,
        scales: np.ndarray,
        normalized_width: int,
        baseline_scale: float,
        category_name: str,
        use_gray_scale: bool = True,
    ) -> float:
        """通过 OK FeatureSet 在指定区域执行多尺度灰度模板识别。"""
        if (
            template is None
            or bgr.ndim != 3
            or bgr.shape[0] < 20
            or bgr.shape[1] < 20
        ):
            return 0.0

        frame_height, frame_width = bgr.shape[:2]
        normalized_height = max(
            1, round(frame_height * normalized_width / frame_width)
        )
        normalized = cv2.resize(
            bgr[:, :, :3],
            (normalized_width, normalized_height),
            interpolation=cv2.INTER_AREA,
        )
        baseline = cv2.resize(
            template,
            (
                max(1, round(template.shape[1] * baseline_scale)),
                max(1, round(template.shape[0] * baseline_scale)),
            ),
            interpolation=cv2.INTER_AREA,
        )
        search_height = max(
            1,
            round(normalized_height * (search_bottom_ratio - search_top_ratio)),
        )
        feature_set = cls._get_ok_feature_set()
        best = 0.0
        for scale in scales:
            candidate = cv2.resize(
                baseline,
                (
                    max(1, round(baseline.shape[1] * float(scale))),
                    max(1, round(baseline.shape[0] * float(scale))),
                ),
                interpolation=cv2.INTER_AREA,
            )
            if (
                candidate.shape[0] > search_height
                or candidate.shape[1] > normalized_width
            ):
                continue
            boxes = feature_set.find_one_feature(
                mat=normalized,
                category_name=category_name,
                threshold=-1.0,
                use_gray_scale=use_gray_scale,
                x=0.0,
                y=search_top_ratio,
                width=1.0,
                height=search_bottom_ratio - search_top_ratio,
                template=candidate,
                limit=1,
            )
            if boxes:
                best = max(best, float(boxes[0].confidence))
        return best

    @classmethod
    def _text_template_confidence(
        cls,
        bgr: np.ndarray,
        template: np.ndarray | None,
        *,
        search_top_ratio: float,
        search_bottom_ratio: float,
        scales: np.ndarray,
    ) -> float:
        return cls._ok_multiscale_confidence(
            bgr,
            template,
            search_top_ratio=search_top_ratio,
            search_bottom_ratio=search_bottom_ratio,
            scales=scales,
            normalized_width=960,
            baseline_scale=0.5,
            category_name="runtime_text_template",
        )

    @classmethod
    def fish_escape_message_confidence(cls, bgr: np.ndarray) -> float:
        """用固定文字模板识别“猶豫了一下，結果讓牠跑掉了……”提示。"""
        return cls._text_template_confidence(
            bgr,
            cls._load_escape_template_mask(),
            search_top_ratio=0.25,
            search_bottom_ratio=1.0,
            scales=np.linspace(0.80, 1.20, 9),
        )

    @classmethod
    def rod_required_message_confidence(cls, bgr: np.ndarray) -> float:
        """识别画面上方的“必須配戴釣竿。”提示。"""
        return cls._text_template_confidence(
            bgr,
            cls._load_rod_required_template_mask(),
            search_top_ratio=0.0,
            search_bottom_ratio=0.45,
            scales=np.linspace(0.75, 1.30, 12),
        )

    @classmethod
    def inventory_full_message_confidence(cls, bgr: np.ndarray) -> float:
        """识别画面上方的“請整理背包後再試一次。”提示。"""
        return cls._text_template_confidence(
            bgr,
            cls._load_inventory_full_template_mask(),
            search_top_ratio=0.0,
            search_bottom_ratio=0.45,
            scales=np.linspace(0.75, 1.30, 12),
        )

    @classmethod
    def _load_inventory_full_icon_template(cls) -> np.ndarray | None:
        if cls._inventory_full_icon_template is None:
            image = cv2.imread(
                str(INVENTORY_FULL_ICON_TEMPLATE_PATH), cv2.IMREAD_COLOR
            )
            if image is not None:
                height, width = image.shape[:2]
                # 静态样本左侧为红圈背包；排除右侧钓鱼按钮与大部分地面。
                cls._inventory_full_icon_template = image[
                    round(height * 0.18) : round(height * 0.94),
                    0 : round(width * 0.38),
                    :3,
                ]
        return cls._inventory_full_icon_template

    @classmethod
    def inventory_full_icon_confidence(cls, bgr: np.ndarray) -> float:
        """用 OK 彩色特征识别钓鱼按钮左侧的红圈背包。"""
        return cls._ok_multiscale_confidence(
            bgr,
            cls._load_inventory_full_icon_template(),
            search_top_ratio=0.25,
            search_bottom_ratio=1.0,
            scales=np.linspace(0.70, 1.35, 14),
            normalized_width=960,
            baseline_scale=0.5,
            category_name="inventory_full_icon",
            use_gray_scale=False,
        )

    @staticmethod
    def _crop_ok_icon_image(image: np.ndarray) -> np.ndarray:
        """裁出圆形按钮核心，排除动态地面和 Space 标签。"""
        hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, np.array([35, 45, 55]), np.array([100, 255, 255]))
        blue = cv2.inRange(hsv, np.array([90, 45, 55]), np.array([132, 255, 255]))
        mask = cv2.bitwise_or(green, blue)
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8)
        )
        count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask)
        if count <= 1:
            return image[:, :, :3]
        component = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y, width, height = (int(value) for value in stats[component, :4])
        left = x + round(width * 0.12)
        right = x + round(width * 0.86)
        top = y + round(height * 0.08)
        bottom = y + round(height * 0.90)
        if right <= left or bottom <= top:
            return image[:, :, :3]
        return image[top:bottom, left:right, :3]

    @classmethod
    def _load_ok_icon_template(cls, path: Path) -> np.ndarray | None:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            return None
        return cls._crop_ok_icon_image(image)

    @classmethod
    def _get_ok_icon_templates(cls) -> dict[str, np.ndarray]:
        if cls._ok_icon_templates is None:
            templates: dict[str, np.ndarray] = {}
            for state_name, path in OK_ICON_TEMPLATE_PATHS.items():
                template = cls._load_ok_icon_template(path)
                if template is not None:
                    templates[state_name] = template
            cls._ok_icon_templates = templates
        return cls._ok_icon_templates

    @staticmethod
    def _rotate_ok_template(template: np.ndarray, angle: float) -> np.ndarray:
        height, width = template.shape[:2]
        matrix = cv2.getRotationMatrix2D(
            (width / 2.0, height / 2.0), angle, 1.0
        )
        return cv2.warpAffine(
            template,
            matrix,
            (width, height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

    @classmethod
    def _get_ok_idle_rotated_templates(cls) -> tuple[np.ndarray, ...]:
        if cls._ok_idle_rotated_templates is None:
            templates: list[np.ndarray] = []
            if OK_IDLE_MOTION_TEMPLATE_PATH.exists():
                capture = cv2.VideoCapture(str(OK_IDLE_MOTION_TEMPLATE_PATH))
                frame_index = 0
                try:
                    while True:
                        success, frame = capture.read()
                        if not success:
                            break
                        # 真实 GIF 共 180 帧；每 12 帧取一个方向，覆盖指针旋转和轻微动画。
                        if frame_index % 12 == 0:
                            templates.append(cls._crop_ok_icon_image(frame))
                        frame_index += 1
                finally:
                    capture.release()
            if not templates:
                # 资源缺失时仍保留合成旋转模板，避免整个指南针恢复功能失效。
                base = cls._get_ok_icon_templates().get("idle_recovery")
                if base is not None:
                    height, width = base.shape[:2]
                    side = max(height, width)
                    top = (side - height) // 2
                    bottom = side - height - top
                    left = (side - width) // 2
                    right = side - width - left
                    square = cv2.copyMakeBorder(
                        base,
                        top,
                        bottom,
                        left,
                        right,
                        cv2.BORDER_REFLECT_101,
                    )
                    templates.extend(
                        cls._rotate_ok_template(square, angle)
                        for angle in range(0, 360, 15)
                    )
            cls._ok_idle_rotated_templates = tuple(templates)
        return cls._ok_idle_rotated_templates

    @classmethod
    def _get_ok_idle_center_template(cls) -> np.ndarray | None:
        """合成不受指针旋转影响的指南针中心黑点锚点。"""
        if cls._ok_idle_center_template is None:
            anchors: list[np.ndarray] = []
            for template in cls._get_ok_idle_rotated_templates():
                height, width = template.shape[:2]
                side = max(12, round(min(height, width) * 0.32))
                center_x = width // 2
                center_y = height // 2
                left = max(0, center_x - side // 2)
                top = max(0, center_y - side // 2)
                anchor = template[top : top + side, left : left + side]
                if anchor.size:
                    anchors.append(
                        cv2.resize(anchor, (48, 48), interpolation=cv2.INTER_AREA)
                    )
            if anchors:
                cls._ok_idle_center_template = np.mean(
                    np.stack(anchors), axis=0
                ).astype(np.uint8)
        return cls._ok_idle_center_template

    @classmethod
    def ok_icon_state_match(
        cls, bgr: np.ndarray
    ) -> tuple[IconState | None, float, float]:
        """返回 OK 状态及分数；未过阈值时保留分数但状态为空。"""
        scores: list[tuple[IconState, float]] = []
        for state_name, template in cls._get_ok_icon_templates().items():
            try:
                confidence = cls._ok_multiscale_confidence(
                    bgr,
                    template,
                    search_top_ratio=0.0,
                    search_bottom_ratio=1.0,
                    scales=np.linspace(0.78, 1.28, 11),
                    normalized_width=cls.OK_ICON_NORMALIZED_WIDTH,
                    baseline_scale=1.0,
                    category_name=f"icon_{state_name}",
                )
                scores.append((IconState(state_name), confidence))
            except (ValueError, cv2.error):
                continue
        if not scores:
            return None, 0.0, 0.0
        scores.sort(key=lambda item: item[1], reverse=True)
        best_state, best_confidence = scores[0]
        second_confidence = scores[1][1] if len(scores) > 1 else 0.0
        if (
            best_confidence >= cls.OK_ICON_MATCH_THRESHOLD
            and best_confidence - second_confidence >= cls.OK_ICON_MATCH_MARGIN
        ):
            return best_state, best_confidence, second_confidence

        # 指南针指针会随人物方向旋转。普通模板未过门槛时，再用 GIF 真实方向帧复核；
        # 仍由 OK FeatureSet 完成匹配，不借用旧像素规则。
        idle_confidence = max(
            (
                confidence
                for state, confidence in scores
                if state == IconState.IDLE_RECOVERY
            ),
            default=0.0,
        )
        for index, template in enumerate(cls._get_ok_idle_rotated_templates()):
            try:
                idle_confidence = max(
                    idle_confidence,
                    cls._ok_multiscale_confidence(
                        bgr,
                        template,
                        search_top_ratio=0.0,
                        search_bottom_ratio=1.0,
                        scales=np.array([0.72, 0.75, 0.78, 0.81, 0.86, 0.94, 1.02, 1.10, 1.18]),
                        normalized_width=cls.OK_ICON_NORMALIZED_WIDTH,
                        baseline_scale=1.0,
                        category_name=f"icon_idle_rotated_{index}",
                    ),
                )
            except (ValueError, cv2.error):
                continue
        non_idle_confidence = max(
            (
                confidence
                for state, confidence in scores
                if state != IconState.IDLE_RECOVERY
            ),
            default=0.0,
        )
        if (
            idle_confidence >= cls.OK_IDLE_ROTATED_MATCH_THRESHOLD
            and idle_confidence - non_idle_confidence
            >= cls.OK_IDLE_ROTATED_MATCH_MARGIN
        ):
            return (
                IconState.IDLE_RECOVERY,
                idle_confidence,
                non_idle_confidence,
            )

        # 实机缩放会显著压低旋转整图模板分数。先要求整图轮廓与其他按钮拉开差距，
        # 再用固定在中心的黑点锚点校正；仍全部通过 OK FeatureSet 完成识别。
        if (
            idle_confidence >= cls.OK_IDLE_CORRECTED_MATCH_THRESHOLD
            and idle_confidence - non_idle_confidence
            >= cls.OK_IDLE_CORRECTED_MATCH_MARGIN
        ):
            center_template = cls._get_ok_idle_center_template()
            try:
                center_confidence = cls._ok_multiscale_confidence(
                    bgr,
                    center_template,
                    search_top_ratio=0.0,
                    search_bottom_ratio=1.0,
                    scales=np.linspace(0.55, 1.55, 21),
                    normalized_width=cls.OK_ICON_NORMALIZED_WIDTH,
                    baseline_scale=1.0,
                    category_name="icon_idle_center_anchor",
                )
            except (ValueError, cv2.error):
                center_confidence = 0.0
            if center_confidence >= cls.OK_IDLE_CENTER_MATCH_THRESHOLD:
                return (
                    IconState.IDLE_RECOVERY,
                    max(idle_confidence, center_confidence),
                    non_idle_confidence,
                )
        return None, max(best_confidence, idle_confidence), second_confidence

    def _on_key_press(
        self, key: keyboard.Key | keyboard.KeyCode | None
    ) -> bool | None:
        if key == keyboard.Key.f7:
            self.calibrate_from_cursor()
        elif key == keyboard.Key.f8:
            self.toggle_monitoring()
        elif key == keyboard.Key.f9:
            self.save_debug_capture()
        elif key == keyboard.Key.esc:
            self.set_monitoring(False)
            self._emit(EventKind.WARNING, "已触发紧急停止。")
        return None

    def _monitor_loop(self) -> None:
        screen: mss.MSS | None = None
        consecutive_failures = 0
        try:
            while not self._shutdown.is_set():
                if not self._enabled.wait(timeout=0.15):
                    consecutive_failures = 0
                    continue

                config = self.config()
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
                    if config.capture_mode == "screen" and screen is None:
                        screen = mss.MSS()
                    frame = self._capture_frame(screen, config)
                    icon_state, signals = self.classify_frame_state(frame[:, :, :3], config)
                    loop_now = time.monotonic()
                    strategy = self._catch_strategy(config)
                    stamina_sample = None
                    escape_message_confidence = 0.0
                    rod_required_confidence: float | None = None
                    inventory_full_confidence: float | None = None
                    if strategy == "stamina_bounce" and (
                        icon_state == IconState.FISH_HOOKED
                        or self._fish_resolution_pending
                    ):
                        # 上钩一经确认便持续扫描整张画面；右下角图标短暂漏识别
                        # 不能中断角色头顶绿条的下降/反弹序列。
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
                    if consecutive_failures:
                        self._emit(
                            EventKind.SUCCESS,
                            f"{source}已恢复，连续失败计数已清零。",
                            monitoring=True,
                        )
                    consecutive_failures = 0
                except Exception as error:  # pragma: no cover - 显示器环境差异
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
                        self._emit(
                            EventKind.ERROR,
                            f"{source}已暂停：连续失败 {total_failures} 次，"
                            f"已用完 {retry_limit} 次自动重试：{error}",
                        )
                        consecutive_failures = 0
                time.sleep(config.poll_interval_ms / 1000)
        except Exception as error:  # pragma: no cover - mss 初始化失败
            self._emit(EventKind.ERROR, f"无法启动识别服务：{error}")
        finally:
            if screen is not None:
                screen.close()

    def _capture_frame(self, screen: mss.MSS | None, config: AppConfig) -> np.ndarray:
        if config.capture_mode == "window":
            if config.target_button_offset is None:
                raise RuntimeError("目标窗口尚未完成按钮校准。")
            target = self._resolve_target_window(config)
            self._maintain_background_hover(target, config)
            roi_width, roi_height = effective_roi_size(
                config, (target.width, target.height)
            )
            if config.window_backend == "ok":
                return self._get_ok_window_backend(target).capture_region(
                    target,
                    config.target_button_offset,
                    roi_width,
                    roi_height,
                )
            return window_target.capture_window_region(
                target.handle,
                config.target_button_offset,
                roi_width,
                roi_height,
            )
        if screen is None:
            raise RuntimeError("屏幕截图服务未初始化。")
        return np.asarray(screen.grab(self._capture_region(config)))

    def _capture_stamina_frame(
        self, screen: mss.MSS | None, config: AppConfig
    ) -> np.ndarray:
        """取得完整游戏画面，供动态体力条和全局提示扫描复用。"""
        if config.capture_mode == "window":
            target = self._resolve_target_window(config)
            self._maintain_background_hover(target, config)
            if config.window_backend == "ok":
                return self._get_ok_window_backend(target).capture_frame(target)
            return window_target.capture_window_frame(target.handle)
        if screen is None:
            raise RuntimeError("屏幕截图服务未初始化。")
        monitor_index = min(max(1, config.monitor_index), len(screen.monitors) - 1)
        return np.asarray(screen.grab(screen.monitors[monitor_index]))

    def _capture_stamina_sample(
        self, screen: mss.MSS | None, config: AppConfig, now: float
    ) -> StaminaBarSample | None:
        # 反弹窗口较短；上钩期间每次主循环都允许完整画面采样，旧配置的 100 ms
        # 不再把真实反弹漏在两次扫描之间。
        interval = max(40, min(75, config.stamina_scan_interval_ms)) / 1000
        if now - self._last_stamina_scan_at < interval:
            return None
        self._last_stamina_scan_at = now
        try:
            frame = self._capture_stamina_frame(screen, config)
        except Exception as error:  # pragma: no cover - 由实际窗口捕捉环境决定
            if now - self._last_stamina_warning_at >= 3.0:
                self._emit(EventKind.WARNING, f"无法读取活鱼体力条：{error}")
                self._last_stamina_warning_at = now
            return None
        game_frame = frame[:, :, :3]
        sample = self.find_stamina_bar(game_frame, require_anchor=True)
        if (
            sample is None
            and self._stamina_bar_seen
            and self._stamina_last_center is not None
        ):
            # OK 锚点偶发动画漏帧时，只接受紧邻上一位置的槽体候选；
            # 不会退回全画面任意绿色像素，也不会改变用户选择的图标识别模式。
            nearby = self.find_stamina_bar(
                game_frame,
                require_anchor=False,
                preferred_center=self._stamina_last_center,
            )
            if nearby is not None:
                distance = float(
                    np.hypot(
                        nearby.center[0] - self._stamina_last_center[0],
                        nearby.center[1] - self._stamina_last_center[1],
                    )
                )
                movement_limit = max(
                    80.0, min(game_frame.shape[0], game_frame.shape[1]) * 0.18
                )
                if distance <= movement_limit:
                    sample = replace(nearby, anchor_confidence=0.0)
        if sample is None:
            if now - self._last_stamina_missing_log_at >= 2.0:
                source = (
                    "目标窗口完整画面"
                    if config.capture_mode == "window"
                    else "当前显示器完整画面"
                )
                self._emit(
                    EventKind.INFO,
                    f"体力条扫描：在{source}中暂未同时确认中鱼图标与"
                    "角色头顶绿条，将继续扫描。",
                    monitoring=True,
                )
                self._last_stamina_missing_log_at = now
            return None
        probe_offset = self._stamina_probe_offset_x
        if probe_offset is None:
            probe_offset = max(1, sample.fill_width // 2)
        return self.classify_stamina_midpoint(game_frame, sample, probe_offset)

    def _capture_escape_message_confidence(
        self, screen: mss.MSS | None, config: AppConfig, now: float
    ) -> float:
        if now - self._last_escape_scan_at < 0.14:
            return 0.0
        self._last_escape_scan_at = now
        try:
            frame = self._capture_stamina_frame(screen, config)
        except Exception as error:  # pragma: no cover - 由实际窗口捕捉环境决定
            if now - self._last_stamina_warning_at >= 3.0:
                self._emit(EventKind.WARNING, f"无法扫描跑鱼提示：{error}")
                self._last_stamina_warning_at = now
            return 0.0
        confidence = self.fish_escape_message_confidence(frame[:, :, :3])
        if confidence >= self.ESCAPE_MESSAGE_MATCH_THRESHOLD:
            self._emit(
                EventKind.INFO,
                f"跑鱼文字模板命中：相似度 {confidence:.3f}。",
                monitoring=True,
            )
        return confidence

    def _capture_blocking_message_confidences(
        self, screen: mss.MSS | None, config: AppConfig, now: float
    ) -> tuple[float, float] | None:
        if (
            now - self._last_blocking_message_scan_at
            < self.BLOCKING_MESSAGE_SCAN_INTERVAL_SECONDS
        ):
            return None
        self._last_blocking_message_scan_at = now
        try:
            frame = self._capture_stamina_frame(screen, config)
        except Exception as error:  # pragma: no cover - 由实际窗口捕捉环境决定
            if now - self._last_blocking_message_warning_at >= 3.0:
                self._emit(EventKind.WARNING, f"无法扫描钓鱼阻塞提示：{error}")
                self._last_blocking_message_warning_at = now
            return None

        bgr = frame[:, :, :3]
        rod_confidence = self.rod_required_message_confidence(bgr)
        inventory_text_confidence = self.inventory_full_message_confidence(bgr)
        inventory_icon_confidence = self.inventory_full_icon_confidence(bgr)
        inventory_confidence = inventory_text_confidence
        if inventory_icon_confidence >= self.INVENTORY_FULL_ICON_MATCH_THRESHOLD:
            inventory_confidence = max(
                inventory_confidence, inventory_icon_confidence
            )
        if rod_confidence >= self.ROD_REQUIRED_MATCH_THRESHOLD:
            self._emit(
                EventKind.INFO,
                f"鱼竿状态文字由 OK 特征识别命中：相似度 {rod_confidence:.3f}。",
                monitoring=True,
            )
        if inventory_text_confidence >= self.INVENTORY_FULL_MATCH_THRESHOLD:
            self._emit(
                EventKind.INFO,
                "背包已满文字由 OK 特征识别命中："
                f"相似度 {inventory_text_confidence:.3f}。",
                monitoring=True,
            )
        if inventory_icon_confidence >= self.INVENTORY_FULL_ICON_MATCH_THRESHOLD:
            self._emit(
                EventKind.INFO,
                "红色背包图标由 OK 彩色特征识别命中："
                f"相似度 {inventory_icon_confidence:.3f}。",
                monitoring=True,
            )
        return rod_confidence, inventory_confidence

    def _resolve_target_window(self, config: AppConfig) -> window_target.WindowInfo:
        target = window_target.resolve_window(
            config.target_window_handle, config.target_window_title
        )
        if target is None:
            raise RuntimeError("找不到已选窗口；请刷新列表并重新选择。")
        if target.handle != config.target_window_handle:
            self.update_config(
                target_window_handle=target.handle,
                target_window_title=target.title,
            )
        return target

    def _get_ok_window_backend(
        self, target: window_target.WindowInfo
    ) -> window_target.OkWindowBackend:
        if self._ok_window_backend is None or self._ok_window_backend.handle != target.handle:
            self._close_ok_window_backend()
            self._ok_window_backend = window_target.OkWindowBackend(target)
        self._ok_window_backend.update(target)
        return self._ok_window_backend

    def _close_ok_window_backend(self) -> None:
        if self._ok_window_backend is not None:
            self._ok_window_backend.close()
            self._ok_window_backend = None

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
            rod_required_confidence, inventory_full_confidence
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

        if self._waiting_for_clear:
            if self._clear_frames >= config.clear_consecutive_frames:
                self._waiting_for_clear = False
                self._schedule_recast(now, config, "收鱼完成")
        elif self._fish_resolution_pending:
            strategy = self._catch_strategy(config)
            if strategy == "stamina_bounce":
                if stamina_sample is not None:
                    # 绿条和中鱼锚点比右下角图标更直接；命中时清掉图标漏识别帧。
                    self._clear_frames = 0
                    if self._observe_stamina_bar(stamina_sample):
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
                self._fish_resolution_pending = False
                self._reset_stamina_tracking()
                self._schedule_recast(now, config, "计时目标已消失")
            elif fish_visible and strategy == "fixed_delay":
                hook_started = self._hook_started_at or now
                if now - hook_started >= config.fallback_collect_delay_seconds:
                    self._collect_fish(
                        now,
                        config,
                        "备用模式 2 计时完成，已按 Space 收鱼。",
                    )
        elif (
            fish_visible
            and self._red_frames >= config.trigger_consecutive_frames
            and now - self._last_press_at >= config.press_cooldown_ms / 1000
        ):
            self._begin_fish_resolution(now, config, stamina_sample)

        if (
            config.auto_recover_idle
            and icon_state == IconState.IDLE_RECOVERY
            and self._idle_frames >= config.recovery_consecutive_frames
            and not self._waiting_for_clear
            and not self._fish_resolution_pending
            and not self._escape_watch_until
            and now - self._last_press_at >= self.CAST_TRANSITION_GRACE_SECONDS
            and now - self._last_recovery_at >= config.recovery_cooldown_ms / 1000
        ):
            self._recover_idle_state(config)
            self._schedule_recast(time.monotonic(), config, "移动恢复完成")

        self._perform_pending_recast(now, icon_state, config)

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

    @staticmethod
    def _catch_strategy(config: AppConfig) -> str:
        if config.catch_strategy in {"fixed_delay", "instant"}:
            return config.catch_strategy
        return "stamina_bounce"

    def _monitoring_details(self, config: AppConfig) -> str:
        """输出一条足以复现当前识别环境的启动日志。"""
        strategy = {
            "stamina_bounce": "模式 1（实验性：中点灰→绿确认）",
            "fixed_delay": f"模式 2（{config.fallback_collect_delay_seconds:.1f} 秒定时）",
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
        common = (
            f"策略 {strategy}；图标识别 {icon_recognizer}；"
            "异常提示识别 OK FeatureSet；"
            f"识别区域 {roi_mode} {roi_width}×{roi_height}；"
            f"轮询 {config.poll_interval_ms} ms；"
            f"临时错误重试 {config.runtime_error_retry_count} 次{pixel_detail}。"
        )
        if config.capture_mode == "window":
            backend = "OK WGC" if config.window_backend == "ok" else "PrintWindow"
            return (
                f"启动参数：后台窗口“{config.target_window_title or '未命名'}”，引擎 {backend}；"
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
        self._hook_started_at = now
        strategy = self._catch_strategy(config)
        if strategy == "instant":
            self._collect_fish(now, config, "模式 3：检测到上钩图标，已立即按 Space 收杆。")
            return
        if strategy == "fixed_delay":
            self._emit(
                EventKind.INFO,
                f"检测到上钩，备用模式 2 开始计时 {config.fallback_collect_delay_seconds:.1f} 秒。",
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
        self._observe_stamina_bar(stamina_sample)

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
        stamina_seen = self._escape_candidate_stamina_seen
        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
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
        self._stamina_bar_seen = True
        width = sample.fill_width
        state = sample.midpoint_state
        self._stamina_sample_count += 1
        observed_at = time.monotonic()
        self._last_stamina_seen_at = observed_at
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
            self._stamina_trough_width = width
        else:
            self._stamina_peak_width = max(previous_peak, width)
            self._stamina_trough_width = min(self._stamina_trough_width, width)
        self._stamina_last_width = width

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

    def _metric_message(self, icon_state: IconState, now: float, config: AppConfig) -> str:
        if self._fish_resolution_pending:
            if self._catch_strategy(config) == "fixed_delay":
                elapsed = max(0.0, now - (self._hook_started_at or now))
                return (
                    f"备用模式 2：已等待 {elapsed:.1f} / "
                    f"{config.fallback_collect_delay_seconds:.1f} 秒"
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
        self._stamina_trough_width = 0
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
            if now - self._last_horse_dismount_at >= 2.0:
                self._press_key("space", config)
                self._last_horse_dismount_at = now
                self._horse_settle_until = now + 1.5
                self._emit(EventKind.SUCCESS, "检测到下马图标，已按一次 Space 下马，等待钓鱼图标恢复。")
            self._horse_guard_state = icon_state
            return True

        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state = None
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

        message_kind, confidence = max(confirmed, key=lambda item: item[1])
        return self._stop_for_blocking_message(message_kind, confidence)

    def _stop_for_blocking_message(self, message_kind: str, confidence: float) -> bool:
        cast_attempts = self._unconfirmed_cast_attempts
        recovery_attempts = self._recovery_attempts_without_success
        self._enabled.clear()
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
            + f"本轮自动抛竿 {cast_attempts} 次，W → S 恢复 {recovery_attempts} 次，"
            + f"OK 特征相似度 {confidence:.3f}。",
            monitoring=False,
        )
        return True
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
        """识别到指南针时短按 W 再 S，刷新开始钓鱼图标。"""
        self._last_recovery_at = time.monotonic()
        self._idle_frames = 0
        self._tap_key("w", config.recovery_key_hold_ms, config)
        time.sleep(config.recovery_pause_ms / 1000)
        self._tap_key("s", config.recovery_key_hold_ms, config)
        if config.capture_mode == "window" and config.auto_resume_fishing:
            self._refresh_hover_before_recast = True
        self._recovery_attempts_without_success += 1
        message = (
            "启动时识别到指南针图标，已执行 W → S 移动恢复。"
            if startup
            else "检测到指南针状态，已执行 W → S 移动恢复。"
        )
        self._emit(EventKind.SUCCESS, message, monitoring=True)
        self._announce_blocking_message_scan_if_needed()

    def _maintain_background_hover(
        self,
        target: window_target.WindowInfo,
        config: AppConfig,
        *,
        force: bool = False,
    ) -> None:
        """让目标窗口持续认为鼠标停在校准点，不改变系统真实光标。"""
        offset = config.target_button_offset
        if offset is None:
            return
        now = time.monotonic()
        if not force and now - self._last_background_hover_at < 0.40:
            return
        if config.window_backend == "ok":
            self._get_ok_window_backend(target).keep_hover(target, offset)
        else:
            window_target.post_mouse_move(target.handle, offset)
        self._last_background_hover_at = now

    def _refresh_background_hover(self, config: AppConfig) -> None:
        """向空白处再回到按钮，触发游戏重新计算首次交互悬停。"""
        if config.capture_mode != "window":
            return
        offset = config.target_button_offset
        if offset is None:
            return
        target = self._resolve_target_window(config)
        roi_width, roi_height = effective_roi_size(
            config, (target.width, target.height)
        )
        neutral = (target.width // 2, target.height // 2)
        separation = max(120, roi_width, roi_height)
        if (
            abs(neutral[0] - offset[0]) < separation
            and abs(neutral[1] - offset[1]) < separation
        ):
            candidate_x = offset[0] - separation * 2
            if candidate_x < 0:
                candidate_x = offset[0] + separation * 2
            neutral = (
                min(max(0, candidate_x), max(0, target.width - 1)),
                min(max(0, offset[1]), max(0, target.height - 1)),
            )

        if config.window_backend == "ok":
            backend = self._get_ok_window_backend(target)
            backend.keep_hover(target, neutral)
            time.sleep(self.BACKGROUND_HOVER_REFRESH_DELAY_SECONDS)
            backend.keep_hover(target, offset)
        else:
            window_target.post_mouse_move(target.handle, neutral)
            time.sleep(self.BACKGROUND_HOVER_REFRESH_DELAY_SECONDS)
            window_target.post_mouse_move(target.handle, offset)
        time.sleep(self.BACKGROUND_HOVER_REFRESH_DELAY_SECONDS)
        self._last_background_hover_at = time.monotonic()
        self._emit(
            EventKind.INFO,
            "W → S 后已刷新后台虚拟悬停，准备发送 Space。",
            monitoring=True,
        )

    def _press_key(self, key: str, config: AppConfig) -> None:
        if config.capture_mode == "window":
            target = self._resolve_target_window(config)
            self._maintain_background_hover(target, config, force=True)
            if config.window_backend == "ok":
                self._get_ok_window_backend(target).tap_key(key)
            else:
                window_target.post_key_tap(target.handle, key, activate_message=True)
            return
        pyautogui.press(key)

    def _tap_key(self, key: str, hold_ms: int, config: AppConfig) -> None:
        if config.capture_mode == "window":
            target = self._resolve_target_window(config)
            self._maintain_background_hover(target, config, force=True)
            if config.window_backend == "ok":
                self._get_ok_window_backend(target).tap_key(key, hold_ms)
            else:
                window_target.post_key_tap(
                    target.handle, key, hold_ms, activate_message=True
                )
            return
        pyautogui.keyDown(key)
        try:
            time.sleep(hold_ms / 1000)
        finally:
            pyautogui.keyUp(key)

    @staticmethod
    def _capture_region(config: AppConfig) -> dict[str, int]:
        if config.button_center is None:
            raise RuntimeError("未设置钓鱼按钮中心")
        x, y = config.button_center
        roi_width, roi_height = effective_roi_size(config)
        return {
            "left": int(x - roi_width // 2),
            "top": int(y - roi_height // 2),
            "width": int(roi_width),
            "height": int(roi_height),
        }

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
        if kind == EventKind.ERROR:
            record_error("fishing engine", message)
        if self._event_callback is not None:
            self._event_callback(EngineEvent(kind=kind, message=message, **details))
