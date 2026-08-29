"""不依赖 UI 的屏幕识别和全局快捷键服务。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

import cv2
import mss
import numpy as np
import pyautogui
from pynput import keyboard

from . import window_target

from .config import DEBUG_IMAGE_PATH, AppConfig, load_config, save_config
from .constants import FISH_ESCAPE_TEMPLATE_PATH
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
    FISH_HOOKED = "fish_hooked"
    IDLE_RECOVERY = "idle_recovery"
    HORSE_MOUNT_PROMPT = "horse_mount_prompt"
    HORSE_DISMOUNT_PROMPT = "horse_dismount_prompt"


@dataclass(frozen=True, slots=True)
class IconColorSignals:
    red_pixels: int
    red_ratio: float
    white_ratio: float
    green_ratio: float
    brown_ratio: float


@dataclass(frozen=True, slots=True)
class StaminaBarSample:
    """动态绿色体力条的一次观测；宽度即当前绿色填充长度。"""

    fill_width: int
    center: tuple[int, int]


@dataclass(slots=True)
class EngineEvent:
    kind: EventKind
    message: str
    red_pixels: int = 0
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
    _escape_template_mask: np.ndarray | None = None

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

        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        self._escape_message_latched = False
        self._last_escape_scan_at = 0.0
        self._last_stamina_scan_at = 0.0
        self._last_stamina_warning_at = 0.0
        self._last_stamina_missing_log_at = 0.0
        self._last_logged_icon_state: IconState | None = None
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
            self._emit(EventKind.INFO, self._monitoring_details(config), monitoring=True)
            if config.capture_mode == "window" and config.window_backend == "ok":
                self._emit(EventKind.INFO, "OK WGC 正在预热首帧，首次启动会在画面到达后自动开始识别。", monitoring=True)
            message = (
                "OK 指定窗口模式已启动；若截图或定向按键不兼容会自动暂停。"
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
            brown_ratio=ratio(brown_mask),
        )

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
        return IconState.NORMAL

    @classmethod
    def classify_frame_state(
        cls, bgr: np.ndarray, config: AppConfig
    ) -> tuple[IconState, IconColorSignals]:
        """先识别白马与马鞍组合，再沿用钓鱼红色像素状态判断。"""
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
        return cls.classify_icon_state(signals.red_pixels, config), signals

    @staticmethod
    def find_stamina_bar(bgr: np.ndarray) -> StaminaBarSample | None:
        """在完整游戏画面中寻找细长的绿色体力条填充，不读取文字内容。"""
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
        # 目标条是“绿色填充 + 右侧深色空槽”的细长进度条；不能只选画面中部，
        # 因为角色移动时它可能出现在任意位置。
        dark_mask = cv2.inRange(hsv, np.array([0, 0, 0]), np.array([179, 255, 90]))
        frame_height, frame_width = bgr.shape[:2]
        candidates: list[tuple[StaminaBarSample, float, bool]] = []
        for index in range(1, count):
            x, y, width, height, area = (int(value) for value in stats[index])
            if not (24 <= width <= 480 and 5 <= height <= 32):
                continue
            if width < height * 2 or area < width * height * 0.55:
                continue
            sample = StaminaBarSample(width, (x + width // 2, y + height // 2))
            # 绿色填充右边应当是尚未消耗的深色进度槽。用条内中段避免圆角和描边干扰。
            core_top = y + max(1, height // 4)
            core_bottom = min(frame_height, y + height - max(1, height // 4))
            track_depth = min(180, max(18, width))
            right = min(frame_width, x + width + track_depth)
            right_band = dark_mask[core_top:core_bottom, x + width : right]
            right_dark_ratio = (
                float(cv2.countNonZero(right_band)) / max(1, right_band.size)
            )
            # 满体力时右侧空槽可能很短，再以条的上下描边作弱特征兜底。
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
            in_focus_area = (
                frame_width * 0.20 <= sample.center[0] <= frame_width * 0.80
                and frame_height * 0.10 <= sample.center[1] <= frame_height * 0.65
            )
            candidates.append((sample, track_score, in_focus_area))
        if not candidates:
            return None
        # 中部只是同分时的弱偏好，不能再作为硬过滤条件；角色和绿条会随画面移动。
        sample, _track_score, _in_focus = max(
            candidates,
            key=lambda item: (item[1], 0.10 if item[2] else 0.0, item[0].fill_width),
        )
        return sample

    @staticmethod
    def _white_text_mask(bgr: np.ndarray) -> np.ndarray:
        """提取游戏提示中的低饱和高亮文字，忽略动态场景颜色。"""
        hsv = cv2.cvtColor(bgr[:, :, :3], cv2.COLOR_BGR2HSV)
        return cv2.inRange(
            hsv, np.array([0, 0, 180]), np.array([179, 105, 255])
        )

    @classmethod
    def _load_escape_template_mask(cls) -> np.ndarray | None:
        if cls._escape_template_mask is not None:
            return cls._escape_template_mask
        template = cv2.imread(str(FISH_ESCAPE_TEMPLATE_PATH), cv2.IMREAD_COLOR)
        if template is None:
            return None
        mask = cls._white_text_mask(template)
        points = cv2.findNonZero(mask)
        if points is None:
            return None
        x, y, width, height = cv2.boundingRect(points)
        cls._escape_template_mask = mask[y : y + height, x : x + width]
        return cls._escape_template_mask

    @classmethod
    def fish_escape_message_confidence(cls, bgr: np.ndarray) -> float:
        """用固定文字模板识别“猶豫了一下，結果讓牠跑掉了……”提示。"""
        if bgr.ndim != 3 or bgr.shape[0] < 40 or bgr.shape[1] < 320:
            return 0.0
        template = cls._load_escape_template_mask()
        if template is None:
            return 0.0

        frame_height, frame_width = bgr.shape[:2]
        # 提示出现在画面下方；只扫描下方约四分之三，减少其他白色 UI 的干扰。
        search = bgr[int(frame_height * 0.25) :, :, :3]
        search_mask = cls._white_text_mask(search)
        normalized_width = 960
        normalized_height = max(
            1, round(search_mask.shape[0] * normalized_width / frame_width)
        )
        search_mask = cv2.resize(
            search_mask,
            (normalized_width, normalized_height),
            interpolation=cv2.INTER_AREA,
        )
        search_mask = cv2.GaussianBlur(search_mask, (3, 3), 0)
        baseline = cv2.resize(
            template,
            (
                max(1, round(template.shape[1] * 0.5)),
                max(1, round(template.shape[0] * 0.5)),
            ),
            interpolation=cv2.INTER_AREA,
        )
        baseline = cv2.GaussianBlur(baseline, (3, 3), 0)

        best = 0.0
        for scale in np.linspace(0.80, 1.20, 9):
            candidate = cv2.resize(
                baseline,
                (
                    max(1, round(baseline.shape[1] * scale)),
                    max(1, round(baseline.shape[0] * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )
            candidate = cv2.GaussianBlur(candidate, (3, 3), 0)
            if (
                candidate.shape[0] > search_mask.shape[0]
                or candidate.shape[1] > search_mask.shape[1]
            ):
                continue
            score_map = cv2.matchTemplate(
                search_mask, candidate, cv2.TM_CCOEFF_NORMED
            )
            if score_map.size:
                best = max(best, float(score_map.max()))
        return best

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
        try:
            while not self._shutdown.is_set():
                if not self._enabled.wait(timeout=0.15):
                    continue

                config = self.config()
                if config.capture_mode == "window":
                    missing_calibration = config.target_button_offset is None
                else:
                    missing_calibration = config.button_center is None
                if missing_calibration:
                    self.set_monitoring(False)
                    continue
                try:
                    if config.capture_mode == "screen" and screen is None:
                        screen = mss.MSS()
                    frame = self._capture_frame(screen, config)
                    icon_state, signals = self.classify_frame_state(frame[:, :, :3], config)
                    loop_now = time.monotonic()
                    strategy = self._catch_strategy(config)
                    stamina_sample = None
                    escape_message_confidence = 0.0
                    if (
                        icon_state == IconState.FISH_HOOKED
                        and strategy == "stamina_bounce"
                    ):
                        stamina_sample = self._capture_stamina_sample(
                            screen, config, loop_now
                        )
                    elif strategy == "stamina_bounce" and (
                        self._fish_resolution_pending
                        or self._escape_watch_until > loop_now
                    ):
                        escape_message_confidence = (
                            self._capture_escape_message_confidence(
                                screen, config, loop_now
                            )
                        )
                    self._process_frame(
                        signals.red_pixels,
                        config,
                        icon_state,
                        stamina_sample,
                        escape_message_confidence,
                    )
                except Exception as error:  # pragma: no cover - 显示器环境差异
                    self._enabled.clear()
                    source = "目标窗口" if config.capture_mode == "window" else "屏幕识别"
                    self._emit(EventKind.ERROR, f"{source}已暂停：{error}")
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
            if config.window_backend == "ok":
                return self._get_ok_window_backend(target).capture_region(
                    target,
                    config.target_button_offset,
                    config.roi_width,
                    config.roi_height,
                )
            return window_target.capture_window_region(
                target.handle,
                config.target_button_offset,
                config.roi_width,
                config.roi_height,
            )
        if screen is None:
            raise RuntimeError("屏幕截图服务未初始化。")
        return np.asarray(screen.grab(self._capture_region(config)))

    def _capture_stamina_frame(
        self, screen: mss.MSS | None, config: AppConfig
    ) -> np.ndarray:
        """仅在上钩期间取得完整游戏画面，以搜索不固定位置的体力条。"""
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
        sample = self.find_stamina_bar(frame[:, :, :3])
        if sample is None:
            if now - self._last_stamina_missing_log_at >= 2.0:
                source = "目标窗口完整画面" if config.capture_mode == "window" else "当前显示器完整画面"
                self._emit(
                    EventKind.INFO,
                    f"体力条扫描：在{source}中暂未找到角色头顶绿条，将继续扫描。",
                    monitoring=True,
                )
                self._last_stamina_missing_log_at = now
            return None
        return sample

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
    ) -> None:
        if icon_state is None:
            icon_state = self.classify_icon_state(red_pixels, config)
        fish_visible = icon_state == IconState.FISH_HOOKED
        now = time.monotonic()

        if icon_state != self._last_logged_icon_state:
            state_name = {
                IconState.NORMAL: "等待上钩",
                IconState.FISH_HOOKED: "上钩图标",
                IconState.IDLE_RECOVERY: "原地失效图标",
                IconState.HORSE_MOUNT_PROMPT: "骑马图标",
                IconState.HORSE_DISMOUNT_PROMPT: "下马图标",
            }[icon_state]
            self._emit(
                EventKind.INFO,
                f"图标状态切换为“{state_name}”：红色像素 {red_pixels}，阈值 {config.fish_red_pixel_threshold}，连续上钩帧 {self._red_frames + (1 if fish_visible else 0)}。",
                monitoring=True,
            )
            self._last_logged_icon_state = icon_state

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

        if (
            not self._waiting_for_clear
            and escape_message_confidence >= self.ESCAPE_MESSAGE_MATCH_THRESHOLD
            and self._record_escape_failure(
                now, config, escape_message_confidence
            )
        ):
            self._perform_pending_recast(now, icon_state, config)
            return
        if self._escape_watch_until and now >= self._escape_watch_until:
            self._finish_escape_watch(now, config)

        if self._waiting_for_clear:
            if self._clear_frames >= config.clear_consecutive_frames:
                self._waiting_for_clear = False
                self._schedule_recast(now, config, "收鱼完成")
        elif self._fish_resolution_pending:
            if not fish_visible and self._clear_frames >= config.clear_consecutive_frames:
                if self._catch_strategy(config) == "stamina_bounce":
                    self._start_escape_watch(now)
                else:
                    self._fish_resolution_pending = False
                    self._reset_stamina_tracking()
                    self._schedule_recast(now, config, "计时目标已消失")
            elif fish_visible:
                strategy = self._catch_strategy(config)
                if strategy == "fixed_delay":
                    hook_started = self._hook_started_at or now
                    if now - hook_started >= config.fallback_collect_delay_seconds:
                        self._collect_fish(
                            now,
                            config,
                            "备用模式 2 计时完成，已按 Space 收鱼。",
                        )
                elif strategy == "stamina_bounce":
                    if self._observe_stamina_bar(stamina_sample):
                        self._collect_fish(
                            now,
                            config,
                            "绿色体力条已下降穿过半条，并在反弹时第二次穿过半条；已按 Space 收鱼。",
                        )
                    elif self._learned_collect_due(now, config):
                        target, margin = self.learned_collect_timing(
                            config.learned_escape_seconds
                        )
                        self._collect_fish(
                            now,
                            config,
                            f"体力条未完成二次半条确认，已按跑鱼学习时间 {target:.1f} 秒兜底收杆（提前 {margin:.1f} 秒）。",
                            allow_without_stamina=True,
                        )
        elif (
            fish_visible
            and self._red_frames >= config.trigger_consecutive_frames
            and now - self._last_press_at >= config.press_cooldown_ms / 1000
        ):
            self._begin_fish_resolution(now, config, stamina_sample)

        if (
            config.auto_recover_idle
            and self._idle_frames >= config.recovery_consecutive_frames
            and not self._waiting_for_clear
            and not self._fish_resolution_pending
            and not self._escape_watch_until
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
            "stamina_bounce": "模式 1（实验性：二次半条确认）",
            "fixed_delay": f"模式 2（{config.fallback_collect_delay_seconds} 秒定时）",
            "instant": "模式 3（上钩立即收杆）",
        }[self._catch_strategy(config)]
        common = (
            f"策略 {strategy}；识别区域 {config.roi_width}×{config.roi_height}；"
            f"轮询 {config.poll_interval_ms} ms；鱼体阈值 {config.fish_red_pixel_threshold} px。"
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
                f"检测到上钩，备用模式 2 开始计时 {config.fallback_collect_delay_seconds} 秒。",
                monitoring=True,
            )
            return
        learned_hint = ""
        if config.learned_escape_seconds > 0:
            target, margin = self.learned_collect_timing(
                config.learned_escape_seconds
            )
            learned_hint = (
                f" 若二次半条识别仍失败，将按已学习的 {target:.1f} 秒"
                f"兜底收杆（比上次跑鱼提前 {margin:.1f} 秒）。"
            )
        self._emit(
            EventKind.INFO,
            "检测到上钩，正在追踪绿色体力条；第一次下降穿过半条只记录，"
            "必须反弹并第二次穿过半条才收鱼。" + learned_hint,
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
            f"{elapsed:.1f} 秒失败。已记录时间；下一次若绿条仍未完成二次半条确认，"
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

    def _finish_escape_watch(self, now: float, config: AppConfig) -> None:
        stamina_seen = self._escape_candidate_stamina_seen
        self._escape_watch_until = 0.0
        self._escape_candidate_elapsed = 0.0
        self._escape_candidate_stamina_seen = False
        if stamina_seen:
            self._schedule_recast(
                now, config, "未出现跑鱼文字，体力条也未完成二次半条确认，已跳过本次目标"
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
        self._stamina_sample_count += 1
        observed_at = time.monotonic()
        if observed_at - self._last_stamina_observation_log_at >= 0.9:
            self._emit(
                EventKind.INFO,
                f"体力条扫描命中：填充 {width} px，位置 {sample.center}，第 {self._stamina_sample_count} 次采样。",
                monitoring=True,
            )
            self._last_stamina_observation_log_at = observed_at
        if self._stamina_peak_width == 0:
            self._stamina_peak_width = width
            self._stamina_trough_width = width
            self._stamina_last_width = width
            self._emit(
                EventKind.INFO,
                f"体力条首帧：填充 {width} px，位置 {sample.center}；第一次下降穿过半条时只记录。",
                monitoring=True,
            )
            return False

        previous_peak = self._stamina_peak_width
        previous_trough = self._stamina_trough_width
        previous_width = self._stamina_last_width
        self._stamina_peak_width = max(previous_peak, width)
        self._stamina_trough_width = min(previous_trough, width)
        self._stamina_last_width = width
        half_limit = max(20, round(self._stamina_peak_width * 0.50))

        if not self._stamina_low_seen:
            crossed_half_down = (
                self._stamina_sample_count >= 2
                and self._stamina_peak_width >= 40
                and previous_width > half_limit
                and width <= half_limit
            )
            if crossed_half_down:
                self._stamina_low_seen = True
                self._emit(
                    EventKind.INFO,
                    f"体力条第一次下降穿过半条：{previous_width} → {width} px，"
                    f"半条阈值 {half_limit} px；本次不收杆，等待反弹后第二次穿过。",
                    monitoring=True,
                )
            return False

        rebound_needed = max(8, round(self._stamina_peak_width * 0.08))
        rise_from_low = width - previous_trough
        if (
            not self._stamina_rebound_started
            and width > previous_width
            and rise_from_low >= rebound_needed
        ):
            self._stamina_rebound_started = True
            self._emit(
                EventKind.INFO,
                f"体力条已确认反弹：最低 {previous_trough} → 当前 {width} px；"
                f"继续等待回升穿过半条 {half_limit} px。",
                monitoring=True,
            )

        crossed_half_up = (
            self._stamina_rebound_started
            and width >= half_limit
            and rise_from_low >= rebound_needed
        )
        if crossed_half_up:
            self._emit(
                EventKind.INFO,
                f"体力条第二次穿过半条：最低 {previous_trough} → 当前 {width} px，"
                f"半条阈值 {half_limit} px；达到收鱼条件。",
                monitoring=True,
            )
        return crossed_half_up

    def _metric_message(self, icon_state: IconState, now: float, config: AppConfig) -> str:
        if self._fish_resolution_pending:
            if self._catch_strategy(config) == "fixed_delay":
                elapsed = max(0.0, now - (self._hook_started_at or now))
                return (
                    f"备用模式 2：已等待 {elapsed:.1f} / "
                    f"{config.fallback_collect_delay_seconds} 秒"
                )
            if self._stamina_peak_width:
                if self._stamina_rebound_started:
                    phase = "已反弹，等待第二次穿过半条"
                elif self._stamina_low_seen:
                    phase = "第一次半条已过，等待反弹"
                else:
                    phase = "等待第一次下降穿过半条"
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
            IconState.NORMAL: "正在等待上钩",
            IconState.FISH_HOOKED: "检测到上钩图标",
            IconState.IDLE_RECOVERY: "检测到原地失效状态，准备移动恢复",
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

    def _cancel_pending_recast(self) -> None:
        self._waiting_for_clear = False
        self._fish_resolution_pending = False
        self._clear_escape_watch()
        self._reset_stamina_tracking()
        self._pending_recast_at = None
        self._pending_recast_reason = ""

    def _schedule_recast(self, now: float, config: AppConfig, reason: str) -> None:
        if not config.auto_resume_fishing:
            self._emit(EventKind.INFO, f"{reason}，等待手动按 Space 再次钓鱼。")
            return
        self._pending_recast_at = now + config.recast_delay_ms / 1000
        self._pending_recast_reason = reason
        self._emit(EventKind.INFO, f"{reason}，将在图标稳定后自动按 Space 继续钓鱼。")

    def _perform_pending_recast(
        self, now: float, icon_state: IconState, config: AppConfig
    ) -> None:
        if self._pending_recast_at is None or now < self._pending_recast_at:
            return
        if icon_state != IconState.NORMAL:
            return
        if now - self._last_press_at < config.press_cooldown_ms / 1000:
            return
        self._press_key("space", config)
        self._last_press_at = now
        reason = self._pending_recast_reason
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._emit(EventKind.SUCCESS, f"{reason}，已按 Space 重新开始钓鱼。", monitoring=True)

    def _recover_idle_state(self, config: AppConfig) -> None:
        """原地超时图标出现时，短按 W 再 S 刷新钓鱼状态。"""
        self._last_recovery_at = time.monotonic()
        self._idle_frames = 0
        self._tap_key("w", config.recovery_key_hold_ms, config)
        time.sleep(config.recovery_pause_ms / 1000)
        self._tap_key("s", config.recovery_key_hold_ms, config)
        self._emit(EventKind.SUCCESS, "检测到原地失效状态，已执行 W → S 移动恢复。", monitoring=True)

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
        return {
            "left": int(x - config.roi_width // 2),
            "top": int(y - config.roi_height // 2),
            "width": int(config.roi_width),
            "height": int(config.roi_height),
        }

    def _reset_detection(self) -> None:
        self._waiting_for_clear = False
        self._red_frames = 0
        self._clear_frames = 0
        self._idle_frames = 0
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._horse_mount_frames = 0
        self._horse_dismount_frames = 0
        self._horse_guard_state = None
        self._horse_settle_until = 0.0
        self._fish_resolution_pending = False
        self._last_logged_icon_state = None
        self._last_stamina_missing_log_at = 0.0
        self._last_background_hover_at = 0.0
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
