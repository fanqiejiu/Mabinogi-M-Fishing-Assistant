"""全局快捷键分发与按住去重；通过任务入口停止，不直接发送游戏输入。"""
from __future__ import annotations

import time
from pynput import keyboard
from fishing_assistant.automation.models import EventKind
from fishing_assistant.config import STOP_HOTKEY_LABELS, normalize_stop_hotkey
from fishing_assistant.diagnostics import record_error

_STOP_KEYS = {name: getattr(keyboard.Key, name) for name in STOP_HOTKEY_LABELS if name != "none"}
_TRACKED_KEYS = frozenset((*_STOP_KEYS.values(), keyboard.Key.f7, keyboard.Key.f8, keyboard.Key.f9))


class HotkeyControlMixin:
    """由 FishingEngine 组装，不单独实例化。"""

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> bool | None:
        # 回调异常不能杀死监听线程，否则所有快捷键都会静默失效。
        try:
            if key not in _TRACKED_KEYS:
                return None
            if key in self._hotkeys_down:
                return None
            self._hotkeys_down.add(key)
            if key == keyboard.Key.f7:
                self.calibrate_from_cursor()
            elif key == keyboard.Key.f8:
                self.toggle_monitoring()
            elif key == keyboard.Key.f9:
                self.request_debug_capture()
            elif key == _STOP_KEYS.get(normalize_stop_hotkey(self.config().stop_hotkey)):
                # 停止后继续玩游戏，不再反复停止或播报。
                if not self.is_monitoring():
                    return None
                # 前台清理背包时助手自己发送的 Esc 不视为用户停止。
                if key == keyboard.Key.esc and time.monotonic() < self._ignore_esc_until:
                    return None
                self.set_monitoring(False)
                self._emit(EventKind.WARNING, "已触发紧急停止。")
        except Exception as error:
            record_error("hotkey handler", error)
            self._emit(EventKind.WARNING, f"快捷键处理出现异常：{error}")
        return None

    def _on_key_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        self._hotkeys_down.discard(key)
