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
        self.update_config(button_center=(x, y))
        self._reset_detection()
        self._emit(EventKind.SUCCESS, f"已校准钓鱼按钮中心：({x}, {y})。")
        return x, y

    def set_monitoring(self, enabled: bool) -> bool:
        if enabled and self.config().button_center is None:
            self._emit(EventKind.WARNING, "请先把鼠标放在圆形按钮中心，再点击校准。")
            return False
        self._reset_detection()
        if enabled:
            self._enabled.set()
            self._emit(EventKind.STATE, "监测已启动，请把游戏保持在前台。", monitoring=True)
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
        if config.button_center is None:
            self._emit(EventKind.WARNING, "请先完成校准，才能保存识别区域。")
            return None
        try:
            with mss.MSS() as screen:
                frame = np.asarray(screen.grab(self._capture_region(config)))
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
    def count_fish_red_pixels(bgr: np.ndarray) -> int:
        """只统计圆形按钮内的红橙色像素，排除附近 UI 的干扰。"""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        low_red = cv2.inRange(
            hsv, np.array([0, 105, 95]), np.array([15, 255, 255])
        )
        high_red = cv2.inRange(
            hsv, np.array([165, 105, 95]), np.array([179, 255, 255])
        )
        red_mask = cv2.bitwise_or(low_red, high_red)

        height, width = red_mask.shape
        circle_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.ellipse(
            circle_mask,
            (width // 2, height // 2),
            (int(width * 0.46), int(height * 0.43)),
            0,
            0,
            360,
            255,
            -1,
        )
        return int(cv2.countNonZero(cv2.bitwise_and(red_mask, circle_mask)))

    @staticmethod
    def classify_icon_state(red_pixels: int, config: AppConfig) -> IconState:
        """区分上钩鱼体、原地失效指针和普通抛竿/等待图标。"""
        if red_pixels >= config.fish_red_pixel_threshold:
            return IconState.FISH_HOOKED
        if config.idle_red_pixel_min <= red_pixels <= config.idle_red_pixel_max:
            return IconState.IDLE_RECOVERY
        return IconState.NORMAL

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
        try:
            with mss.MSS() as screen:
                while not self._shutdown.is_set():
                    if not self._enabled.wait(timeout=0.15):
                        continue

                    config = self.config()
                    if config.button_center is None:
                        self.set_monitoring(False)
                        continue
                    try:
                        frame = np.asarray(screen.grab(self._capture_region(config)))
                        red_pixels = self.count_fish_red_pixels(frame[:, :, :3])
                        self._process_frame(red_pixels, config)
                    except Exception as error:  # pragma: no cover - 显示器环境差异
                        self._enabled.clear()
                        self._emit(EventKind.ERROR, f"屏幕识别已暂停：{error}")
                    time.sleep(config.poll_interval_ms / 1000)
        except Exception as error:  # pragma: no cover - mss 初始化失败
            self._emit(EventKind.ERROR, f"无法启动屏幕识别服务：{error}")

    def _process_frame(self, red_pixels: int, config: AppConfig) -> None:
        icon_state = self.classify_icon_state(red_pixels, config)
        fish_visible = icon_state == IconState.FISH_HOOKED
        now = time.monotonic()

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
            pyautogui.press("space")
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
        pyautogui.press("space")
        self._last_press_at = now
        reason = self._pending_recast_reason
        self._pending_recast_at = None
        self._pending_recast_reason = ""
        self._emit(EventKind.SUCCESS, f"{reason}，已按 Space 重新开始钓鱼。", monitoring=True)

    def _recover_idle_state(self, config: AppConfig) -> None:
        """原地超时图标出现时，短按 W 再 S 刷新钓鱼状态。"""
        self._last_recovery_at = time.monotonic()
        self._idle_frames = 0
        self._tap_key("w", config.recovery_key_hold_ms)
        time.sleep(config.recovery_pause_ms / 1000)
        self._tap_key("s", config.recovery_key_hold_ms)
        self._emit(EventKind.SUCCESS, "检测到原地失效状态，已执行 W → S 移动恢复。", monitoring=True)

    @staticmethod
    def _tap_key(key: str, hold_ms: int) -> None:
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
