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


@dataclass(slots=True)
class EngineEvent:
    kind: EventKind
    message: str
    red_pixels: int = 0
    fish_visible: bool = False
    monitoring: bool = False
    icon_state: IconState = IconState.NORMAL
    debug_image: Path | None = None


EventCallback = Callable[[EngineEvent], None]


class FishingEngine:
    """后台识别服务，可被桌面 UI、命令行或未来的其他界面复用。"""

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
        self._emit(EventKind.INFO, "助手已就绪：F7 校准，F8 开始/暂停，F9 保存识别区域。")

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
            message = f"已校准目标窗口“{target.title}”内按钮：({offset[0]}, {offset[1]})。"
        else:
            self.update_config(button_center=(x, y))
            message = f"已校准钓鱼按钮中心：({x}, {y})。"
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
                self._emit(EventKind.WARNING, "请先把鼠标放在圆形按钮中心，再点击校准。")
                return False
        self._reset_detection()
        if enabled:
            self._enabled.set()
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
                    self._process_frame(signals.red_pixels, config, icon_state)
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
        self, red_pixels: int, config: AppConfig, icon_state: IconState | None = None
    ) -> None:
        if icon_state is None:
            icon_state = self.classify_icon_state(red_pixels, config)
        fish_visible = icon_state == IconState.FISH_HOOKED
        now = time.monotonic()

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

        if self._waiting_for_clear:
            if self._clear_frames >= config.clear_consecutive_frames:
                self._waiting_for_clear = False
                self._schedule_recast(now, config, "收鱼完成")
        elif (
            self._red_frames >= config.trigger_consecutive_frames
            and now - self._last_press_at >= config.press_cooldown_ms / 1000
        ):
            self._press_key("space", config)
            self._last_press_at = now
            self._waiting_for_clear = True
            self._emit(
                EventKind.SUCCESS,
                f"检测到上钩，已按 Space（红色像素 {red_pixels}）。",
                red_pixels=red_pixels,
                fish_visible=True,
                monitoring=True,
                icon_state=icon_state,
            )

        if (
            config.auto_recover_idle
            and self._idle_frames >= config.recovery_consecutive_frames
            and not self._waiting_for_clear
            and now - self._last_recovery_at >= config.recovery_cooldown_ms / 1000
        ):
            self._recover_idle_state(config)
            self._schedule_recast(time.monotonic(), config, "移动恢复完成")

        self._perform_pending_recast(now, icon_state, config)

        if now - self._last_metric_at >= 0.18:
            message = {
                IconState.NORMAL: "正在等待上钩",
                IconState.FISH_HOOKED: "检测到上钩图标",
                IconState.IDLE_RECOVERY: "检测到原地失效状态，准备移动恢复",
                IconState.HORSE_MOUNT_PROMPT: "检测到骑马图标，已阻止自动按键",
                IconState.HORSE_DISMOUNT_PROMPT: "检测到下马图标，正在恢复钓鱼状态",
            }[icon_state]
            self._emit(
                EventKind.METRIC,
                message,
                red_pixels=red_pixels,
                fish_visible=fish_visible,
                monitoring=True,
                icon_state=icon_state,
            )
            self._last_metric_at = now

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

    def _press_key(self, key: str, config: AppConfig) -> None:
        if config.capture_mode == "window":
            target = self._resolve_target_window(config)
            if config.window_backend == "ok":
                self._get_ok_window_backend(target).tap_key(key)
            else:
                window_target.post_key_tap(target.handle, key, activate_message=True)
            return
        pyautogui.press(key)

    def _tap_key(self, key: str, hold_ms: int, config: AppConfig) -> None:
        if config.capture_mode == "window":
            target = self._resolve_target_window(config)
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
