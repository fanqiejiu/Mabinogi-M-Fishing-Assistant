"""健壮性回归测试：覆盖配置加载、热键、状态机与并发边界。"""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from pynput import keyboard

from fishing_assistant.config import AppConfig, default_config, load_config
from fishing_assistant.engine import (
    EventKind,
    FishingEngine,
    IconColorSignals,
    IconState,
)
from fishing_assistant.window_target import WindowInfo


def _load_raw_config(text: str) -> AppConfig:
    with tempfile.TemporaryDirectory() as directory:
        config_path = Path(directory) / "fishing_config.json"
        config_path.write_text(text, encoding="utf-8")
        with patch("fishing_assistant.config.CONFIG_PATH", config_path):
            return load_config()


class ConfigRobustnessTests(unittest.TestCase):
    """语法正确但结构损坏的配置必须回落到默认值，而不是让应用无法启动。"""

    def test_json_list_config_falls_back_to_defaults(self) -> None:
        self.assertEqual(_load_raw_config("[1, 2, 3]"), default_config())

    def test_null_schema_version_falls_back_to_defaults(self) -> None:
        config = _load_raw_config(json.dumps({"schema_version": None}))
        self.assertEqual(config.schema_version, default_config().schema_version)

    def test_scalar_button_center_falls_back_to_none(self) -> None:
        config = _load_raw_config(
            json.dumps({"schema_version": 14, "button_center": 5})
        )
        self.assertIsNone(config.button_center)

    def test_string_button_center_is_not_split_into_characters(self) -> None:
        config = _load_raw_config(
            json.dumps({"schema_version": 14, "button_center": "ab"})
        )
        self.assertIsNone(config.button_center)

    def test_github_auto_check_preference_is_respected(self) -> None:
        config = _load_raw_config(
            json.dumps({"schema_version": 14, "github_auto_check": False})
        )
        self.assertFalse(config.github_auto_check)

    def test_github_auto_check_defaults_to_enabled(self) -> None:
        config = _load_raw_config(json.dumps({"schema_version": 14}))
        self.assertTrue(config.github_auto_check)


class MonitorLoopRobustnessTests(unittest.TestCase):
    """监测线程不能因非法配置死亡，死亡时也不能假装仍在监测。"""

    def _window_config(self, **changes: object) -> AppConfig:
        return AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_button_offset=(1600, 860),
            **changes,
        )

    def test_negative_poll_interval_does_not_kill_monitor_loop(self) -> None:
        engine = FishingEngine()
        engine._config = self._window_config(poll_interval_ms=-5)
        engine._enabled.set()
        frame = np.zeros((180, 160, 3), dtype=np.uint8)
        signals = IconColorSignals(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        processed = []

        def count_frames(*_args, **_kwargs) -> None:
            processed.append(1)
            if len(processed) >= 2:
                engine._shutdown.set()

        with patch.object(engine, "_capture_frame", return_value=frame), patch.object(
            FishingEngine,
            "classify_frame_state",
            return_value=(IconState.NORMAL, signals),
        ), patch.object(engine, "_process_frame", side_effect=count_frames):
            engine._monitor_loop()

        self.assertEqual(len(processed), 2)

    def test_monitor_loop_fatal_error_clears_monitoring_flag(self) -> None:
        events = []
        engine = FishingEngine(events.append)
        engine._enabled.set()

        with patch.object(
            engine, "config", side_effect=RuntimeError("fatal")
        ), patch("fishing_assistant.engine.record_error"):
            engine._monitor_loop()

        self.assertFalse(engine.is_monitoring())
        self.assertTrue(
            any(event.kind == EventKind.ERROR for event in events)
        )


class RecoveryCancellationTests(unittest.TestCase):
    """Esc / 暂停必须是可靠的送键取消边界。"""

    def test_pause_during_recovery_skips_second_key(self) -> None:
        engine = FishingEngine()
        engine._enabled.set()
        config = AppConfig(recovery_pause_ms=0)
        taps = []

        def tap(key: str, _hold_ms: int, _config: AppConfig) -> None:
            taps.append(key)
            if key == "w":
                engine._enabled.clear()

        with patch.object(engine, "_tap_key", side_effect=tap):
            engine._recover_idle_state(config)

        engine._shutdown.set()
        self.assertEqual(taps, ["w"])

    def test_disabling_auto_resume_cancels_pending_recast(self) -> None:
        engine = FishingEngine()
        config = AppConfig(auto_resume_fishing=False)
        engine._pending_recast_at = 1.0
        engine._pending_recast_reason = "测试"

        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._perform_pending_recast(2.0, IconState.READY_TO_CAST, config)

        press.assert_not_called()
        self.assertIsNone(engine._pending_recast_at)


class HotkeyListenerRobustnessTests(unittest.TestCase):
    """快捷键回调里的异常不能杀死 pynput 监听线程。"""

    def test_hotkey_callback_swallows_and_logs_errors(self) -> None:
        engine = FishingEngine()
        with patch.object(
            engine, "calibrate_from_cursor", side_effect=RuntimeError("boom")
        ), patch("fishing_assistant.engine.record_error") as recorded:
            try:
                engine._on_key_press(keyboard.Key.f7)
            except RuntimeError:
                self.fail("快捷键回调让异常逃逸，会静默杀死 pynput 监听线程。")
        recorded.assert_called_once()

    def test_start_monitoring_survives_window_vanishing_mid_start(self) -> None:
        """验证通过后、启用瞬间窗口消失：应返回 False 而不是抛异常。"""
        target = WindowInfo(101, "瑪奇 Mobile", 0, 0, 1920, 1080)
        engine = FishingEngine()
        engine._config = AppConfig(
            capture_mode="window",
            window_backend="printwindow",
            catch_strategy="instant",
            target_window_handle=target.handle,
            target_window_title=target.title,
            target_button_offset=(1600, 860),
        )

        with patch.object(
            engine,
            "_resolve_target_window",
            side_effect=[target, RuntimeError("窗口已关闭")],
        ):
            try:
                result = engine.set_monitoring(True)
            except RuntimeError:
                self.fail("set_monitoring 让 RuntimeError 逃逸到快捷键线程。")

        self.assertFalse(result)
        self.assertFalse(engine.is_monitoring())


class HorseDismountLatchTests(unittest.TestCase):
    """README 契约：检测到下马图标时只尝试一次下马。"""

    def test_persistent_dismount_prompt_presses_space_only_once(self) -> None:
        engine = FishingEngine()
        config = AppConfig()
        with patch.object(engine, "_press_key") as press, patch(
            "fishing_assistant.engine.time.monotonic"
        ) as clock:
            for now in (100.0, 100.1, 102.5, 105.0, 107.5, 110.0):
                clock.return_value = now
                engine._process_frame(
                    205, config, IconState.HORSE_DISMOUNT_PROMPT
                )
        press.assert_called_once_with("space", config)

    def test_dismount_can_retry_after_prompt_cycles(self) -> None:
        engine = FishingEngine()
        config = AppConfig()
        with patch.object(engine, "_press_key") as press, patch(
            "fishing_assistant.engine.time.monotonic"
        ) as clock:
            for now in (100.0, 100.1):
                clock.return_value = now
                engine._process_frame(
                    205, config, IconState.HORSE_DISMOUNT_PROMPT
                )
            clock.return_value = 103.0
            engine._process_frame(0, config, IconState.NORMAL)
            for now in (104.0, 104.1):
                clock.return_value = now
                engine._process_frame(
                    205, config, IconState.HORSE_DISMOUNT_PROMPT
                )
        self.assertEqual(press.call_count, 2)


class StrategySwitchTests(unittest.TestCase):
    """钓鱼进行中切换收鱼策略不能让本轮楔住。"""

    def test_switching_to_instant_mid_hook_collects(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
            press.assert_not_called()
            switched = config.copy(catch_strategy="instant")
            engine._process_frame(1985, switched, IconState.FISH_HOOKED)
        press.assert_called_once_with("space")


class OkBackendLifecycleTests(unittest.TestCase):
    """WGC backend 的建立必须串行化，避免双 session 洩漏。"""

    def test_ok_backend_creation_is_serialized(self) -> None:
        created = []

        class SlowBackend:
            def __init__(self, info: WindowInfo) -> None:
                created.append(self)
                self.handle = info.handle
                import time as _time

                _time.sleep(0.05)

            def update(self, _info: WindowInfo) -> None:
                pass

            def close(self) -> None:
                pass

        engine = FishingEngine()
        target = WindowInfo(101, "瑪奇 Mobile", 0, 0, 1920, 1080)
        with patch(
            "fishing_assistant.engine.window_target.OkWindowBackend", SlowBackend
        ):
            threads = [
                threading.Thread(
                    target=lambda: engine._get_ok_window_backend(target)
                )
                for _ in range(2)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

        self.assertEqual(len(created), 1)


class EscapeWatchCharacterizationTests(unittest.TestCase):
    """锁定 escape watch 既有行为，防止无测试路径回归。"""

    def _run_watch(self, *, stamina_seen: bool) -> tuple[FishingEngine, list]:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            clear_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        events = []
        engine = FishingEngine(events.append)
        with patch("fishing_assistant.engine.pyautogui.press") as press, patch(
            "fishing_assistant.engine.time.monotonic"
        ) as clock:
            clock.return_value = 100.0
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
            if stamina_seen:
                engine._stamina_bar_seen = True
            clock.return_value = 101.0
            engine._process_frame(0, config, IconState.NORMAL)
            clock.return_value = 104.0
            engine._process_frame(0, config, IconState.NORMAL)
            press.assert_not_called()
        return engine, events

    def test_hook_vanishing_without_stamina_is_treated_as_false_positive(
        self,
    ) -> None:
        engine, events = self._run_watch(stamina_seen=False)
        self.assertIsNone(engine._pending_recast_at)
        self.assertFalse(engine._fish_resolution_pending)
        self.assertTrue(
            any("误识别" in event.message for event in events)
        )

    def test_hook_vanishing_after_stamina_seen_schedules_recast(self) -> None:
        engine, _events = self._run_watch(stamina_seen=True)
        self.assertIsNotNone(engine._pending_recast_at)


if __name__ == "__main__":
    unittest.main()
