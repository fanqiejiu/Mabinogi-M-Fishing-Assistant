"""健壮性回归测试：覆盖配置加载、热键、状态机与并发边界。"""

import json
import tempfile
import threading
import time
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

    def test_infinite_number_in_config_falls_back_to_defaults(self) -> None:
        # json.loads 会把 1e309 解析成 infinity；int(inf) 抛 OverflowError。
        self.assertEqual(
            _load_raw_config('{"schema_version": 1e309}'), default_config()
        )

    def test_infinite_coordinate_is_dropped(self) -> None:
        config = _load_raw_config(
            json.dumps({"schema_version": 14, "button_center": [1e309, 0]})
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

    def test_pending_recast_rechecks_live_auto_resume_setting(self) -> None:
        """monitor 帧首快照仍为 True、用户随后关闭：送键前必须读实时设置。"""
        engine = FishingEngine()
        engine._config = AppConfig(auto_resume_fishing=False)
        stale_frame_config = AppConfig(auto_resume_fishing=True)
        engine._pending_recast_at = 1.0
        engine._pending_recast_reason = "测试"

        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._perform_pending_recast(
                2.0, IconState.READY_TO_CAST, stale_frame_config
            )

        press.assert_not_called()

    def test_stop_restart_during_recovery_still_cancels_second_key(self) -> None:
        """W 之后的停顿内快速停止又启动（ABA）：旧恢复序列不得补送 S。"""
        engine = FishingEngine()
        engine._enabled.set()
        config = AppConfig(recovery_pause_ms=0)
        taps = []

        def tap(key: str, _hold_ms: int, _config: AppConfig) -> None:
            taps.append(key)
            if key == "w":
                engine.set_monitoring(False)
                engine._enabled.set()

        with patch.object(engine, "_tap_key", side_effect=tap):
            engine._recover_idle_state(config)

        engine._shutdown.set()
        self.assertEqual(taps, ["w"])


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

    def test_start_monitoring_survives_window_vanishing_before_hover(self) -> None:
        """第二次 resolve 成功、hover 阶段窗口才消失：同样不得抛异常。"""
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
            engine, "_resolve_target_window", return_value=target
        ), patch.object(
            engine,
            "_maintain_background_hover",
            side_effect=RuntimeError("窗口已关闭"),
        ):
            try:
                result = engine.set_monitoring(True)
            except RuntimeError:
                self.fail("hover 阶段的 RuntimeError 逃逸出 set_monitoring。")

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


class BlockingMessagePriorityTests(unittest.TestCase):
    """早退后的相似度不可参与排序：阻塞讯息用固定优先序。"""

    def test_blocking_message_priority_is_fixed_not_score_based(self) -> None:
        events = []
        engine = FishingEngine(events.append)
        engine._enabled.set()
        with patch("fishing_assistant.engine.record_error"):
            # 两种提示各确认两帧；rod 分数被早退压低、inventory 分数较高。
            engine._handle_blocking_messages(0.72, 0.95)
            engine._handle_blocking_messages(0.72, 0.95)

        error_events = [e for e in events if e.kind == EventKind.ERROR]
        self.assertEqual(len(error_events), 1)
        self.assertIn("必須配戴釣竿", error_events[0].message)


class ScaleSafetyInvariantTests(unittest.TestCase):
    """尺度限缩的安全不变式：hint 只收判定级命中、重试闸覆盖死区。"""

    def test_icon_hint_floor_not_below_decision_threshold(self) -> None:
        # 过渡帧的垃圾命中（0.70-0.85）若能写入 hint，会把该模板限缩在
        # 错误尺度上且分数落入重试死区，永远救不回来。
        self.assertGreaterEqual(
            FishingEngine.OK_ICON_HINT_MIN_CONFIDENCE,
            FishingEngine.OK_ICON_MATCH_THRESHOLD,
        )

    def test_retry_gate_covers_all_hint_recordable_scores(self) -> None:
        self.assertLessEqual(
            FishingEngine.OK_SCALE_RETRY_MIN_CONFIDENCE,
            FishingEngine.OK_SCALE_HINT_MIN_CONFIDENCE,
        )

    def test_restricted_decision_on_state_change_is_verified_full_range(
        self,
    ) -> None:
        """限缩扫描下的「转态判定」必须全幅复验，以全幅结果为准。"""
        calls = []

        def fake_score(bgr, scales_override=None):
            calls.append(scales_override is None)
            if scales_override is None:
                return [
                    (IconState.HORSE_MOUNT_PROMPT, 0.90),
                    (IconState.WAITING_BITE, 0.50),
                ]
            return [
                (IconState.WAITING_BITE, 0.95),
                (IconState.HORSE_MOUNT_PROMPT, 0.60),
            ]

        FishingEngine._scale_hints["icon_waiting_bite"] = 1.0
        FishingEngine._last_decided_state = IconState.WAITING_BITE
        try:
            with patch.object(
                FishingEngine, "_score_icon_templates", side_effect=fake_score
            ):
                state, _conf, _second = FishingEngine.ok_icon_state_match(
                    np.zeros((180, 160, 3), dtype=np.uint8)
                )
        finally:
            FishingEngine._scale_hints.clear()
            FishingEngine._last_decided_state = None

        self.assertEqual(calls, [True, False])
        self.assertEqual(state, IconState.WAITING_BITE)

    def test_restricted_decision_on_same_state_skips_verification(self) -> None:
        calls = []

        def fake_score(bgr, scales_override=None):
            calls.append(scales_override is None)
            return [
                (IconState.WAITING_BITE, 0.95),
                (IconState.READY_TO_CAST, 0.50),
            ]

        FishingEngine._scale_hints["icon_waiting_bite"] = 1.0
        FishingEngine._last_decided_state = IconState.WAITING_BITE
        try:
            with patch.object(
                FishingEngine, "_score_icon_templates", side_effect=fake_score
            ):
                state, _conf, _second = FishingEngine.ok_icon_state_match(
                    np.zeros((180, 160, 3), dtype=np.uint8)
                )
        finally:
            FishingEngine._scale_hints.clear()
            FishingEngine._last_decided_state = None

        self.assertEqual(calls, [True])
        self.assertEqual(state, IconState.WAITING_BITE)


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

    def test_backend_close_waits_for_inflight_capture(self) -> None:
        """borrow/use/close 竞态：关闭必须等待进行中的截图完成。"""
        order = []
        capture_started = threading.Event()
        release_capture = threading.Event()

        class SlowBackend:
            def __init__(self, info: WindowInfo) -> None:
                self.handle = info.handle

            def update(self, _info: WindowInfo) -> None:
                pass

            def capture_region(self, *_args) -> np.ndarray:
                order.append("cap_start")
                capture_started.set()
                release_capture.wait(2)
                order.append("cap_end")
                return np.zeros((180, 160, 4), dtype=np.uint8)

            def close(self) -> None:
                order.append("close")

        target = WindowInfo(101, "瑪奇 Mobile", 0, 0, 1920, 1080)
        engine = FishingEngine()
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_window_handle=target.handle,
            target_window_title=target.title,
            target_button_offset=(1600, 860),
        )
        with patch(
            "fishing_assistant.engine.window_target.OkWindowBackend", SlowBackend
        ), patch.object(
            engine, "_resolve_target_window", return_value=target
        ), patch.object(engine, "_maintain_background_hover"):
            worker = threading.Thread(
                target=lambda: engine._capture_frame(None, config)
            )
            worker.start()
            self.assertTrue(capture_started.wait(2))
            closer = threading.Thread(target=engine._close_ok_window_backend)
            closer.start()
            time.sleep(0.15)
            release_capture.set()
            worker.join(2)
            closer.join(2)

        self.assertEqual(order, ["cap_start", "cap_end", "close"])


class ScaleHintTests(unittest.TestCase):
    """多尺度匹配应记住上次命中的尺度：窗口尺寸在会话内不变。"""

    def test_scales_are_reordered_around_recorded_hint(self) -> None:
        FishingEngine._scale_hints.pop("unit_test_category", None)
        scales = np.array([0.8, 0.9, 1.0, 1.1, 1.2])
        default_order = FishingEngine._ordered_scales(
            "unit_test_category", scales
        )
        self.assertEqual(default_order, [0.8, 0.9, 1.0, 1.1, 1.2])

        FishingEngine._scale_hints["unit_test_category"] = 1.1
        hinted = FishingEngine._ordered_scales("unit_test_category", scales)
        self.assertEqual(hinted[0], 1.1)
        self.assertEqual(sorted(hinted), default_order)

    def test_confident_icon_match_records_scale_hint(self) -> None:
        import cv2

        from fishing_assistant.constants import OK_ICON_TEMPLATE_PATHS

        FishingEngine._scale_hints.clear()
        frame = cv2.imread(
            str(OK_ICON_TEMPLATE_PATHS["waiting_bite"]), cv2.IMREAD_COLOR
        )
        self.assertIsNotNone(frame)
        # 本测试针对模板扫描路径的尺度 hint 行为；关闭 v2 走 legacy 路径。
        state, _signals = FishingEngine.classify_frame_state(
            frame, AppConfig(recognition_backend="ok", v2_vision_enabled=False)
        )
        self.assertEqual(state, IconState.WAITING_BITE)
        self.assertIn("icon_waiting_bite", FishingEngine._scale_hints)


class ScaleRestrictionTests(unittest.TestCase):
    """每个模板只信自己的历史命中尺度；不同模板之间尺度不可互推。"""

    FULL_SCALES = np.linspace(0.78, 1.28, 11)

    def setUp(self) -> None:
        FishingEngine._scale_hints.clear()
        FishingEngine._no_decision_streak = 0
        FishingEngine._last_decided_state = None

    def test_scales_full_without_own_hint_even_if_others_hinted(self) -> None:
        FishingEngine._scale_hints["icon_other"] = 1.0
        scales = FishingEngine._category_scan_scales(
            "icon_mine", self.FULL_SCALES
        )
        self.assertEqual(len(scales), 11)

    def test_scales_restricted_with_own_hint(self) -> None:
        FishingEngine._scale_hints["icon_mine"] = 1.02
        restricted = FishingEngine._category_scan_scales(
            "icon_mine", self.FULL_SCALES
        )
        self.assertEqual(len(restricted), 3)
        self.assertTrue(
            all(abs(float(scale) - 1.02) <= 0.075 for scale in restricted)
        )

    def test_no_decision_streak_triggers_periodic_full_rescan(self) -> None:
        FishingEngine._scale_hints["icon_mine"] = 1.02
        FishingEngine._no_decision_streak = 8
        scales = FishingEngine._category_scan_scales(
            "icon_mine", self.FULL_SCALES
        )
        self.assertEqual(len(scales), 11)

    def test_decision_resets_no_decision_streak(self) -> None:
        import cv2

        from fishing_assistant.constants import OK_ICON_TEMPLATE_PATHS

        FishingEngine._no_decision_streak = 5
        frame = cv2.imread(
            str(OK_ICON_TEMPLATE_PATHS["waiting_bite"]), cv2.IMREAD_COLOR
        )
        self.assertIsNotNone(frame)
        state, _confidence, _second = FishingEngine.ok_icon_state_match(frame)
        self.assertEqual(state, IconState.WAITING_BITE)
        self.assertEqual(FishingEngine._no_decision_streak, 0)

    def test_all_reference_icons_recognized_with_hints_active(self) -> None:
        """相似模板（上马/下马）不能因其他模板的 hint 而漏判。"""
        import cv2

        from fishing_assistant.constants import OK_ICON_TEMPLATE_PATHS

        for state_name, path in OK_ICON_TEMPLATE_PATHS.items():
            frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
            state, _signals = FishingEngine.classify_frame_state(
                frame, AppConfig(recognition_backend="ok")
            )
            self.assertEqual(state, IconState(state_name))


class PendingResolutionCadenceTests(unittest.TestCase):
    """上钩期间主循环必须缩短睡眠：反弹窗口按 ~60ms 节奏设计。"""

    def test_pending_resolution_uses_short_poll_sleep(self) -> None:
        engine = FishingEngine()
        engine._config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_button_offset=(1600, 860),
            poll_interval_ms=75,
        )
        engine._enabled.set()
        engine._fish_resolution_pending = True
        frame = np.zeros((180, 160, 3), dtype=np.uint8)
        signals = IconColorSignals(0, 0.0, 0.0, 0.0, 0.0, 0.0)
        sleeps = []

        def record_sleep(seconds: float) -> None:
            sleeps.append(seconds)
            engine._shutdown.set()

        with patch.object(engine, "_capture_frame", return_value=frame), patch.object(
            FishingEngine,
            "classify_frame_state",
            return_value=(IconState.FISH_HOOKED, signals),
        ), patch.object(engine, "_process_frame"), patch.object(
            engine, "_capture_stamina_sample", return_value=None
        ), patch.object(
            engine, "_capture_escape_message_confidence", return_value=0.0
        ), patch(
            "fishing_assistant.engine.time.sleep", side_effect=record_sleep
        ):
            engine._monitor_loop()

        self.assertTrue(sleeps)
        self.assertLessEqual(sleeps[-1], 0.020)


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
