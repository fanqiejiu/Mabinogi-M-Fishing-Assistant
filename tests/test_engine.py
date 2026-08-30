import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from fishing_assistant.config import (
    AppConfig,
    effective_roi_size,
    load_config,
    resolution_label_for_size,
    scaled_roi_size,
)
from fishing_assistant.constants import (
    FISH_ESCAPE_TEMPLATE_PATH,
    INVENTORY_FULL_ICON_TEMPLATE_PATH,
    INVENTORY_FULL_TEMPLATE_PATH,
    OK_ICON_TEMPLATE_PATHS,
    OK_IDLE_MOTION_TEMPLATE_PATH,
    OK_STAMINA_ANCHOR_TEMPLATE_PATH,
    ROD_REQUIRED_TEMPLATE_PATH,
)
from fishing_assistant.engine import (
    EventKind,
    FishingEngine,
    IconColorSignals,
    IconState,
    StaminaBarSample,
)
from fishing_assistant.window_target import WindowInfo


class FishingEngineTests(unittest.TestCase):
    def test_default_icon_recognition_mode_is_ok(self) -> None:
        self.assertEqual(AppConfig().recognition_backend, "ok")

    def test_old_config_migrates_to_explicit_ok_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fishing_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 10,
                        "recognition_backend": "pixel",
                    }
                ),
                encoding="utf-8",
            )
            with patch("fishing_assistant.config.CONFIG_PATH", config_path):
                config = load_config()

        self.assertEqual(config.schema_version, 14)
        self.assertEqual(config.recognition_backend, "ok")
        self.assertEqual(config.runtime_error_retry_count, 5)
        self.assertTrue(config.auto_scale_roi)
        self.assertEqual(config.fallback_collect_delay_seconds, 14.0)
        self.assertIsInstance(config.fallback_collect_delay_seconds, float)

    def test_integer_fixed_delay_migrates_to_float(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fishing_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "schema_version": 13,
                        "fallback_collect_delay_seconds": 5,
                    }
                ),
                encoding="utf-8",
            )
            with patch("fishing_assistant.config.CONFIG_PATH", config_path):
                config = load_config()

        self.assertEqual(config.schema_version, 14)
        self.assertEqual(config.fallback_collect_delay_seconds, 5.0)
        self.assertIsInstance(config.fallback_collect_delay_seconds, float)

    def test_auto_roi_scales_common_resolutions_and_tolerates_window_borders(self) -> None:
        self.assertEqual(scaled_roi_size(1920, 1080), (160, 180))
        self.assertEqual(scaled_roi_size(1918, 1030), (160, 180))
        self.assertEqual(scaled_roi_size(2560, 1440), (214, 240))
        self.assertEqual(scaled_roi_size(3840, 2160), (320, 360))
        self.assertEqual(resolution_label_for_size(1918, 1030), "1920 × 1080")

    def test_manual_roi_is_not_scaled(self) -> None:
        config = AppConfig(
            auto_scale_roi=False,
            selected_resolution="3840 × 2160",
            roi_width=222,
            roi_height=244,
        )
        self.assertEqual(effective_roi_size(config), (222, 244))

    def test_runtime_error_retry_default_is_five(self) -> None:
        self.assertEqual(AppConfig().runtime_error_retry_count, 5)

    def test_monitor_loop_retries_temporary_window_errors_then_recovers(self) -> None:
        events = []
        engine = FishingEngine(events.append)
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_button_offset=(1600, 860),
            runtime_error_retry_count=2,
            poll_interval_ms=0,
        )
        engine._config = config  # type: ignore[attr-defined]
        engine._enabled.set()  # type: ignore[attr-defined]
        frame = np.zeros((186, 160, 3), dtype=np.uint8)
        signals = IconColorSignals(0, 0.0, 0.0, 0.0, 0.0, 0.0)

        def finish_after_success(*_args, **_kwargs) -> None:
            engine._shutdown.set()  # type: ignore[attr-defined]

        with patch.object(
            engine,
            "_capture_frame",
            side_effect=[RuntimeError("temporary"), RuntimeError("temporary"), frame],
        ) as capture, patch.object(
            engine, "_close_ok_window_backend"
        ) as close_backend, patch.object(
            FishingEngine,
            "classify_frame_state",
            return_value=(IconState.NORMAL, signals),
        ), patch.object(
            engine, "_process_frame", side_effect=finish_after_success
        ), patch(
            "fishing_assistant.engine.time.sleep"
        ):
            engine._monitor_loop()  # type: ignore[attr-defined]

        self.assertEqual(capture.call_count, 3)
        self.assertEqual(close_backend.call_count, 2)
        self.assertTrue(engine.is_monitoring())
        self.assertEqual(
            sum(event.kind == EventKind.WARNING for event in events), 2
        )
        self.assertTrue(any("已恢复" in event.message for event in events))

    def test_monitor_loop_pauses_after_retry_limit_is_exhausted(self) -> None:
        events = []
        engine = FishingEngine()
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_button_offset=(1600, 860),
            runtime_error_retry_count=2,
            poll_interval_ms=0,
        )
        engine._config = config  # type: ignore[attr-defined]
        engine._enabled.set()  # type: ignore[attr-defined]

        def collect(event) -> None:
            events.append(event)
            if event.kind == EventKind.ERROR:
                engine._shutdown.set()  # type: ignore[attr-defined]

        engine.set_event_callback(collect)
        with patch.object(
            engine, "_capture_frame", side_effect=RuntimeError("temporary")
        ) as capture, patch.object(
            engine, "_close_ok_window_backend"
        ) as close_backend, patch("fishing_assistant.engine.time.sleep"):
            engine._monitor_loop()  # type: ignore[attr-defined]

        self.assertEqual(capture.call_count, 3)
        self.assertEqual(close_backend.call_count, 2)
        self.assertFalse(engine.is_monitoring())
        self.assertTrue(
            any("已用完 2 次自动重试" in event.message for event in events)
        )

    def test_waiting_frame_has_no_red_fish_signal(self) -> None:
        waiting = np.zeros((180, 160, 3), dtype=np.uint8)
        self.assertEqual(FishingEngine.count_fish_red_pixels(waiting), 0)

    def test_red_fish_signal_exceeds_default_threshold(self) -> None:
        fish_frame = np.zeros((180, 160, 3), dtype=np.uint8)
        fish_frame[60:100, 60:100] = (0, 0, 255)
        self.assertGreater(
            FishingEngine.count_fish_red_pixels(fish_frame),
            AppConfig().fish_red_pixel_threshold,
        )

    def test_icon_states_keep_rod_warning_and_fish_separate(self) -> None:
        config = AppConfig()
        self.assertEqual(
            FishingEngine.classify_icon_state(766, config),
            IconState.READY_TO_CAST,
        )
        self.assertEqual(
            FishingEngine.classify_icon_state(365, config).value, "idle_recovery"
        )
        self.assertEqual(
            FishingEngine.classify_icon_state(1985, config).value, "fish_hooked"
        )

    def test_rod_color_signature_recovers_when_red_count_is_low(self) -> None:
        hsv = np.zeros((180, 160, 3), dtype=np.uint8)
        hsv[:, :] = (60, 170, 220)
        hsv[105:155, 20:140] = (105, 220, 220)
        hsv[35:118, 92:104] = (20, 180, 160)

        state, signals = FishingEngine.classify_frame_state(
            cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR),
            AppConfig(recognition_backend="pixel"),
        )

        self.assertLess(signals.red_pixels, AppConfig().idle_red_pixel_min)
        self.assertEqual(state, IconState.READY_TO_CAST)

    def test_waiting_bite_icon_is_not_ready_to_cast(self) -> None:
        hsv = np.zeros((168, 151, 3), dtype=np.uint8)
        hsv[:, :] = (60, 170, 220)
        hsv[52:108, 45:101] = (0, 0, 245)

        state, _signals = FishingEngine.classify_frame_state(
            cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR),
            AppConfig(recognition_backend="pixel"),
        )

        self.assertEqual(state, IconState.WAITING_BITE)

    def test_f8_start_arms_cast_and_ready_icon_casts_once(self) -> None:
        config = AppConfig(
            button_center=(1700, 900),
            catch_strategy="instant",
            recast_delay_ms=10000,
        )
        engine = FishingEngine()
        engine._config = config  # type: ignore[attr-defined]
        with patch.object(engine, "_prepare_stamina_view"), patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            self.assertTrue(engine.set_monitoring(True))
            self.assertIsNotNone(engine._pending_recast_at)  # type: ignore[attr-defined]
            engine._process_frame(766, config, IconState.READY_TO_CAST)
            engine._process_frame(0, config, IconState.WAITING_BITE)
        engine._enabled.clear()  # type: ignore[attr-defined]

        press.assert_called_once_with("space")
        self.assertIsNone(engine._pending_recast_at)  # type: ignore[attr-defined]

    def test_startup_idle_recovery_casts_on_rod_without_second_ws(self) -> None:
        config = AppConfig(
            button_center=(1700, 900),
            catch_strategy="instant",
            recovery_consecutive_frames=1,
            recovery_cooldown_ms=0,
            recovery_pause_ms=0,
        )
        engine = FishingEngine()
        engine._config = config  # type: ignore[attr-defined]

        with patch.object(engine, "_prepare_stamina_view"), patch.object(
            engine, "_tap_key"
        ) as tap_key, patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            engine.set_monitoring(True)
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)
            engine._process_frame(766, config, IconState.READY_TO_CAST)
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)

        engine._enabled.clear()  # type: ignore[attr-defined]
        self.assertEqual(
            [call.args[0] for call in tap_key.call_args_list],
            ["w", "s"],
        )
        press.assert_called_once_with("space")

    def test_startup_compass_uses_short_probe_then_casts_on_rod(self) -> None:
        config = AppConfig(
            button_center=(1700, 900),
            catch_strategy="instant",
            recovery_consecutive_frames=8,
            recovery_cooldown_ms=0,
            recovery_pause_ms=0,
        )
        engine = FishingEngine()
        engine._config = config  # type: ignore[attr-defined]

        with patch.object(engine, "_prepare_stamina_view"), patch.object(
            engine, "_tap_key"
        ) as tap_key, patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            engine.set_monitoring(True)
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)
            tap_key.assert_not_called()
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)
            self.assertEqual(
                [call.args[0] for call in tap_key.call_args_list],
                ["w", "s"],
            )
            press.assert_not_called()
            engine._process_frame(766, config, IconState.READY_TO_CAST)

        engine._enabled.clear()  # type: ignore[attr-defined]
        press.assert_called_once_with("space")
    def test_pending_recast_never_presses_waiting_bite_icon(self) -> None:
        config = AppConfig(press_cooldown_ms=0)
        engine = FishingEngine()
        engine._pending_recast_at = 0.0  # type: ignore[attr-defined]
        engine._pending_recast_reason = "测试"  # type: ignore[attr-defined]

        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(0, config, IconState.WAITING_BITE)

        press.assert_not_called()
        self.assertIsNotNone(engine._pending_recast_at)  # type: ignore[attr-defined]

    def test_recent_space_blocks_ws_during_icon_transition(self) -> None:
        config = AppConfig(
            recovery_consecutive_frames=1,
            recovery_cooldown_ms=0,
        )
        engine = FishingEngine()
        engine._last_press_at = 99.0  # type: ignore[attr-defined]

        with patch("fishing_assistant.engine.time.monotonic", return_value=100.0), patch.object(
            engine, "_tap_key"
        ) as tap_key:
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)

        tap_key.assert_not_called()

    def test_horse_icons_override_fishing_states(self) -> None:
        def horse_frame(with_dismount_arrow: bool) -> np.ndarray:
            hsv = np.zeros((180, 160, 3), dtype=np.uint8)
            hsv[:, :] = (60, 170, 220)
            hsv[48:102, 48:98] = (0, 0, 245)
            hsv[76:94, 76:98] = (16, 180, 155)
            if with_dismount_arrow:
                hsv[112:130, 68:92] = (0, 220, 240)
            return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        pixel_config = AppConfig(recognition_backend="pixel")
        mount_state, _ = FishingEngine.classify_frame_state(
            horse_frame(False), pixel_config
        )
        dismount_state, _ = FishingEngine.classify_frame_state(
            horse_frame(True), pixel_config
        )
        self.assertEqual(mount_state, IconState.HORSE_MOUNT_PROMPT)
        self.assertEqual(dismount_state, IconState.HORSE_DISMOUNT_PROMPT)

    def test_ok_mode_recognizes_all_reference_icons(self) -> None:
        config = AppConfig(recognition_backend="ok")
        for state_name, path in OK_ICON_TEMPLATE_PATHS.items():
            with self.subTest(state=state_name):
                frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
                self.assertIsNotNone(frame)
                state, signals = FishingEngine.classify_frame_state(frame, config)
                self.assertEqual(state, IconState(state_name))
                if state == IconState.IDLE_RECOVERY:
                    self.assertEqual(signals.recognition_source, "compass_pixel")
                    self.assertGreaterEqual(
                        signals.recognition_confidence,
                        FishingEngine.COMPASS_PIXEL_MATCH_THRESHOLD,
                    )
                else:
                    self.assertEqual(signals.recognition_source, "ok_feature")
                    self.assertGreaterEqual(
                        signals.recognition_confidence,
                        FishingEngine.OK_ICON_MATCH_THRESHOLD,
                    )

    def test_ok_mode_recognizes_real_compass_motion_frames(self) -> None:
        config = AppConfig(recognition_backend="ok")
        capture = cv2.VideoCapture(str(OK_IDLE_MOTION_TEMPLATE_PATH))
        target_frames = {8, 45, 97, 143, 178}
        checked: set[int] = set()
        frame_index = 0
        try:
            while True:
                success, frame = capture.read()
                if not success:
                    break
                if frame_index in target_frames:
                    state, signals = FishingEngine.classify_frame_state(frame, config)
                    self.assertEqual(state, IconState.IDLE_RECOVERY)
                    self.assertEqual(signals.recognition_source, "compass_pixel")
                    self.assertGreaterEqual(
                        signals.recognition_confidence,
                        FishingEngine.COMPASS_PIXEL_MATCH_THRESHOLD,
                    )
                    checked.add(frame_index)
                frame_index += 1
        finally:
            capture.release()
        self.assertEqual(checked, target_frames)

    def test_ok_mode_uses_compass_pixels_on_live_wgc_frame(self) -> None:
        fixture_names = (
            "ok_idle_compass_wgc_low_confidence.png",
            "ok_idle_compass_clear.png",
        )
        for fixture_name in fixture_names:
            with self.subTest(fixture=fixture_name):
                frame = cv2.imread(
                    str(Path(__file__).parent / "fixtures" / fixture_name),
                    cv2.IMREAD_COLOR,
                )
                self.assertIsNotNone(frame)

                with patch.object(
                    FishingEngine, "ok_icon_state_match"
                ) as ok_match:
                    state, signals = FishingEngine.classify_frame_state(
                        frame, AppConfig(recognition_backend="ok")
                    )

                ok_match.assert_not_called()
                self.assertEqual(state, IconState.IDLE_RECOVERY)
                self.assertEqual(signals.recognition_source, "compass_pixel")
                self.assertGreaterEqual(
                    signals.recognition_confidence,
                    FishingEngine.COMPASS_PIXEL_MATCH_THRESHOLD,
                )

    def test_ok_mode_never_falls_back_to_red_pixels(self) -> None:
        red_frame = np.zeros((180, 160, 3), dtype=np.uint8)
        red_frame[45:135, 35:125] = (0, 0, 255)
        with patch.object(
            FishingEngine, "analyze_icon_colors"
        ) as pixel_analyzer, patch.object(
            FishingEngine,
            "ok_icon_state_match",
            return_value=(None, 0.82, 0.80),
        ) as ok_match:
            state, signals = FishingEngine.classify_frame_state(
                red_frame, AppConfig(recognition_backend="ok")
            )

        pixel_analyzer.assert_not_called()
        ok_match.assert_called_once()
        self.assertEqual(state, IconState.NORMAL)
        self.assertEqual(signals.recognition_source, "ok_feature")
        self.assertAlmostEqual(signals.recognition_confidence, 0.82)

    def test_pixel_mode_is_explicit_and_does_not_call_ok_icon_matcher(self) -> None:
        red_frame = np.zeros((180, 160, 3), dtype=np.uint8)
        red_frame[45:135, 35:125] = (0, 0, 255)
        with patch.object(FishingEngine, "ok_icon_state_match") as ok_match:
            state, signals = FishingEngine.classify_frame_state(
                red_frame, AppConfig(recognition_backend="pixel")
            )

        ok_match.assert_not_called()
        self.assertEqual(state, IconState.FISH_HOOKED)
        self.assertEqual(signals.recognition_source, "compat_pixel")

    def test_horse_prompts_block_mount_and_correct_dismount(self) -> None:
        config = AppConfig(press_cooldown_ms=0)
        engine = FishingEngine()
        engine._pending_recast_at = 0.0  # type: ignore[attr-defined]
        with patch.object(engine, "_press_key") as press:
            engine._process_frame(0, config, IconState.HORSE_MOUNT_PROMPT)
            engine._process_frame(0, config, IconState.HORSE_MOUNT_PROMPT)
            press.assert_not_called()
            engine._process_frame(205, config, IconState.HORSE_DISMOUNT_PROMPT)
            engine._process_frame(205, config, IconState.HORSE_DISMOUNT_PROMPT)
        press.assert_called_once_with("space", config)

    def test_fixed_delay_mode_collects_then_recasts_automatically(self) -> None:
        config = AppConfig(
            catch_strategy="fixed_delay",
            fallback_collect_delay_seconds=0,
            trigger_consecutive_frames=1,
            clear_consecutive_frames=1,
            press_cooldown_ms=0,
            recast_delay_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
            engine._process_frame(766, config, IconState.READY_TO_CAST)
        self.assertEqual(press.call_args_list[0].args, ("space",))
        self.assertEqual(press.call_args_list[1].args, ("space",))

    def test_instant_mode_collects_as_soon_as_hook_is_detected(self) -> None:
        config = AppConfig(
            catch_strategy="instant",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
        press.assert_called_once_with("space")

    def test_mode_one_false_hook_without_stamina_never_collects_or_recasts(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            clear_consecutive_frames=1,
            press_cooldown_ms=0,
            recast_delay_ms=0,
        )
        engine = FishingEngine()
        with patch(
            "fishing_assistant.engine.time.monotonic",
            side_effect=[100.0, 100.4, 101.0],
        ), patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
            engine._process_frame(0, config, IconState.NORMAL)
            engine._process_frame(0, config, IconState.NORMAL)
        press.assert_not_called()
        self.assertFalse(engine._fish_resolution_pending)  # type: ignore[attr-defined]
        self.assertIsNone(engine._pending_recast_at)  # type: ignore[attr-defined]

    def test_stamina_bar_must_drop_then_rebound_before_collecting(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        peak = StaminaBarSample(132, (400, 300))
        trough = StaminaBarSample(48, (400, 300))
        rebound = StaminaBarSample(72, (400, 300))
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=peak)
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=trough)
            press.assert_not_called()
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=rebound)
        press.assert_called_once_with("space")

    def test_tracking_that_starts_below_half_does_not_guess_first_crossing(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(55, (80, 80)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(45, (500, 320)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(132, (500, 320)))
        press.assert_not_called()
    def test_stamina_bar_without_rebound_is_not_collected(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(132, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(48, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(56, (400, 300)))
        press.assert_not_called()

    def test_stamina_rebound_works_when_first_peak_is_seen_late(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(80, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(38, (560, 480)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(57, (120, 720)))
        press.assert_called_once_with("space")

    def test_first_half_crossing_and_small_jitter_do_not_collect(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(132, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(64, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(65, (400, 300)))
            press.assert_not_called()
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(46, (400, 300)))
            engine._process_frame(1985, config, IconState.FISH_HOOKED, stamina_sample=StaminaBarSample(72, (400, 300)))
        press.assert_called_once_with("space")

    def test_rod_required_template_matches_scaled_top_notice(self) -> None:
        template = cv2.imread(str(ROD_REQUIRED_TEMPLATE_PATH), cv2.IMREAD_COLOR)
        self.assertIsNotNone(template)
        scaled = cv2.resize(template, None, fx=0.90, fy=0.90)
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        top, left = 45, 650
        frame[top : top + scaled.shape[0], left : left + scaled.shape[1]] = scaled

        confidence = FishingEngine.rod_required_message_confidence(frame)

        self.assertGreaterEqual(
            confidence, FishingEngine.ROD_REQUIRED_MATCH_THRESHOLD
        )

    def test_inventory_full_template_matches_scaled_top_notice(self) -> None:
        template = cv2.imread(
            str(INVENTORY_FULL_TEMPLATE_PATH), cv2.IMREAD_COLOR
        )
        self.assertIsNotNone(template)
        scaled = cv2.resize(template, None, fx=0.90, fy=0.90)
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        top, left = 45, 650
        frame[top : top + scaled.shape[0], left : left + scaled.shape[1]] = scaled

        confidence = FishingEngine.inventory_full_message_confidence(frame)

        self.assertGreaterEqual(
            confidence, FishingEngine.INVENTORY_FULL_MATCH_THRESHOLD
        )

    def test_inventory_full_red_backpack_uses_ok_color_feature(self) -> None:
        sample = cv2.imread(
            str(INVENTORY_FULL_ICON_TEMPLATE_PATH), cv2.IMREAD_COLOR
        )
        self.assertIsNotNone(sample)
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        top = frame.shape[0] - sample.shape[0]
        left = frame.shape[1] - sample.shape[1]
        frame[top:, left:] = sample

        confidence = FishingEngine.inventory_full_icon_confidence(frame)

        self.assertGreaterEqual(
            confidence, FishingEngine.INVENTORY_FULL_ICON_MATCH_THRESHOLD
        )

    def test_inventory_full_icon_does_not_match_unrelated_fishing_icon(self) -> None:
        sample = cv2.imread(
            str(OK_ICON_TEMPLATE_PATHS["ready_to_cast"]), cv2.IMREAD_COLOR
        )
        self.assertIsNotNone(sample)
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        top = frame.shape[0] - sample.shape[0]
        left = frame.shape[1] - sample.shape[1]
        frame[top:, left:] = sample

        confidence = FishingEngine.inventory_full_icon_confidence(frame)

        self.assertLess(
            confidence, FishingEngine.INVENTORY_FULL_ICON_MATCH_THRESHOLD
        )

    def test_three_unconfirmed_casts_arm_rod_status_scan(self) -> None:
        config = AppConfig(button_center=(1700, 900))
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            for attempt in range(FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD):
                engine._pending_recast_at = 0.0  # type: ignore[attr-defined]
                engine._pending_recast_reason = f"测试 {attempt}"  # type: ignore[attr-defined]
                engine._perform_pending_recast(100.0 + attempt, IconState.READY_TO_CAST, config)

        self.assertEqual(
            engine._unconfirmed_cast_attempts,  # type: ignore[attr-defined]
            FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD,
        )
        self.assertTrue(engine._should_scan_blocking_messages())  # type: ignore[attr-defined]
        self.assertEqual(press.call_count, FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD)

    def test_three_idle_recoveries_also_arm_rod_status_scan(self) -> None:
        config = AppConfig(recovery_pause_ms=0)
        engine = FishingEngine()
        with patch.object(engine, "_tap_key") as tap_key:
            for _attempt in range(FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD):
                engine._recover_idle_state(config)

        self.assertEqual(
            engine._recovery_attempts_without_success,  # type: ignore[attr-defined]
            FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD,
        )
        self.assertTrue(engine._should_scan_blocking_messages())  # type: ignore[attr-defined]
        self.assertEqual(tap_key.call_count, FishingEngine.BLOCKING_MESSAGE_RETRY_THRESHOLD * 2)

    def test_successful_waiting_state_clears_failed_start_tracking(self) -> None:
        config = AppConfig()
        engine = FishingEngine()
        engine._enabled.set()  # type: ignore[attr-defined]
        engine._unconfirmed_cast_attempts = 3  # type: ignore[attr-defined]
        engine._recovery_attempts_without_success = 3  # type: ignore[attr-defined]
        engine._rod_required_hits = 1  # type: ignore[attr-defined]
        engine._inventory_full_hits = 1  # type: ignore[attr-defined]

        engine._process_frame(
            0,
            config,
            IconState.WAITING_BITE,
            rod_required_confidence=0.99,
        )

        self.assertTrue(engine.is_monitoring())
        self.assertEqual(engine._unconfirmed_cast_attempts, 0)  # type: ignore[attr-defined]
        self.assertEqual(engine._recovery_attempts_without_success, 0)  # type: ignore[attr-defined]
        self.assertEqual(engine._rod_required_hits, 0)  # type: ignore[attr-defined]
        self.assertEqual(engine._inventory_full_hits, 0)  # type: ignore[attr-defined]
        engine._enabled.clear()  # type: ignore[attr-defined]

    def test_rod_required_notice_stops_after_two_confirmed_frames(self) -> None:
        config = AppConfig()
        events = []
        engine = FishingEngine(events.append)
        engine._enabled.set()  # type: ignore[attr-defined]
        engine._unconfirmed_cast_attempts = 3  # type: ignore[attr-defined]

        with patch("fishing_assistant.engine.record_error"):
            engine._process_frame(
                365,
                config,
                IconState.IDLE_RECOVERY,
                rod_required_confidence=0.90,
            )
            self.assertTrue(engine.is_monitoring())
            engine._process_frame(
                365,
                config,
                IconState.IDLE_RECOVERY,
                rod_required_confidence=0.91,
            )

        self.assertFalse(engine.is_monitoring())
        error_events = [event for event in events if event.kind.value == "error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("必須配戴釣竿", error_events[0].message)
        self.assertIn("监测已停止", error_events[0].message)

    def test_inventory_full_notice_stops_after_two_confirmed_frames(self) -> None:
        config = AppConfig()
        events = []
        engine = FishingEngine(events.append)
        engine._enabled.set()  # type: ignore[attr-defined]
        engine._unconfirmed_cast_attempts = 3  # type: ignore[attr-defined]

        with patch("fishing_assistant.engine.record_error"):
            engine._process_frame(
                365,
                config,
                IconState.IDLE_RECOVERY,
                inventory_full_confidence=0.90,
            )
            self.assertTrue(engine.is_monitoring())
            engine._process_frame(
                365,
                config,
                IconState.IDLE_RECOVERY,
                inventory_full_confidence=0.91,
            )

        self.assertFalse(engine.is_monitoring())
        error_events = [event for event in events if event.kind.value == "error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("請整理背包後再試一次", error_events[0].message)
        self.assertIn("监测已停止", error_events[0].message)

    def test_escape_message_template_matches_scaled_game_notice(self) -> None:
        template = cv2.imread(str(FISH_ESCAPE_TEMPLATE_PATH), cv2.IMREAD_COLOR)
        self.assertIsNotNone(template)
        scaled = cv2.resize(template, None, fx=0.90, fy=0.90)
        frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        top, left = 760, 650
        frame[top : top + scaled.shape[0], left : left + scaled.shape[1]] = scaled

        confidence = FishingEngine.fish_escape_message_confidence(frame)

        self.assertGreaterEqual(
            confidence, FishingEngine.ESCAPE_MESSAGE_MATCH_THRESHOLD
        )

    def test_escape_failure_records_duration_and_early_target(self) -> None:
        config = AppConfig(catch_strategy="stamina_bounce")
        engine = FishingEngine()
        engine._config = config  # type: ignore[attr-defined]
        engine._fish_resolution_pending = True  # type: ignore[attr-defined]
        engine._hook_started_at = 100.0  # type: ignore[attr-defined]
        with patch("fishing_assistant.engine.save_config"), patch(
            "fishing_assistant.engine.record_error"
        ), patch.object(engine, "_schedule_recast") as schedule:
            handled = engine._record_escape_failure(114.0, config, 0.91)

        self.assertTrue(handled)
        self.assertAlmostEqual(engine.config().learned_escape_seconds, 14.0)
        target, margin = FishingEngine.learned_collect_timing(14.0)
        self.assertAlmostEqual(target, 12.6)
        self.assertAlmostEqual(margin, 1.4)
        schedule.assert_called_once()

    def test_learned_time_collects_even_when_stamina_is_not_found(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            learned_escape_seconds=14.0,
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        engine._fish_resolution_pending = True  # type: ignore[attr-defined]
        engine._hook_started_at = 100.0  # type: ignore[attr-defined]
        with patch("fishing_assistant.engine.time.monotonic", return_value=112.7), patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            engine._process_frame(1985, config, IconState.FISH_HOOKED)
        press.assert_called_once_with("space")

    def test_finds_green_stamina_fill_without_reading_text(self) -> None:
        hsv = np.zeros((180, 320, 3), dtype=np.uint8)
        hsv[80:94, 60:192] = (62, 210, 230)
        frame = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        sample = FishingEngine.find_stamina_bar(frame)
        self.assertIsNotNone(sample)
        self.assertEqual(sample.fill_width, 132)  # type: ignore[union-attr]
        self.assertEqual(sample.center, (127, 88))  # type: ignore[union-attr]

    def test_production_stamina_detector_requires_ok_fish_anchor(self) -> None:
        frame = np.full((360, 640, 3), 155, dtype=np.uint8)
        green = cv2.cvtColor(
            np.array([[[62, 210, 230]]], dtype=np.uint8), cv2.COLOR_HSV2BGR
        )[0, 0]
        frame[145:169, 355:540] = (40, 40, 40)
        frame[150:164, 360:460] = green
        anchor = cv2.imread(str(OK_STAMINA_ANCHOR_TEMPLATE_PATH), cv2.IMREAD_COLOR)
        self.assertIsNotNone(anchor)
        top, left = 80, 415
        frame[top : top + anchor.shape[0], left : left + anchor.shape[1]] = anchor

        sample = FishingEngine.find_stamina_bar(frame, require_anchor=True)
        self.assertIsNotNone(sample)
        self.assertEqual(sample.fill_width, 100)  # type: ignore[union-attr]
        self.assertGreaterEqual(
            sample.anchor_confidence,  # type: ignore[union-attr]
            FishingEngine.STAMINA_ANCHOR_MATCH_THRESHOLD,
        )

        frame[top : top + anchor.shape[0], left : left + anchor.shape[1]] = 155
        self.assertIsNone(FishingEngine.find_stamina_bar(frame, require_anchor=True))

    def test_stamina_rebound_continues_when_hook_icon_temporarily_misses(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            clear_consecutive_frames=2,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(
                1985, config, IconState.FISH_HOOKED, StaminaBarSample(132, (400, 300))
            )
            engine._process_frame(
                0, config, IconState.NORMAL, StaminaBarSample(64, (398, 301))
            )
            engine._process_frame(
                0, config, IconState.NORMAL, StaminaBarSample(46, (402, 299))
            )
            engine._process_frame(
                0, config, IconState.NORMAL, StaminaBarSample(72, (404, 302))
            )

        press.assert_called_once_with("space")
    def test_stamina_detector_prioritizes_character_zone_over_top_left_hud(self) -> None:
        hsv = np.zeros((1080, 1920, 3), dtype=np.uint8)
        hsv[80:94, 114:270] = (62, 210, 230)  # 左上角固定生命条
        hsv[190:204, 844:966] = (62, 210, 230)  # 角色头顶体力条

        sample = FishingEngine.find_stamina_bar(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))

        self.assertIsNotNone(sample)
        self.assertEqual(sample.fill_width, 122)  # type: ignore[union-attr]
        self.assertEqual(sample.center, (906, 198))  # type: ignore[union-attr]

    def test_stamina_detector_prefers_dark_progress_track_at_any_position(self) -> None:
        frame = np.full((360, 640, 3), 160, dtype=np.uint8)
        green = cv2.cvtColor(
            np.array([[[62, 210, 230]]], dtype=np.uint8), cv2.COLOR_HSV2BGR
        )[0, 0]
        frame[145:169, 355:540] = (40, 40, 40)  # 目标条的深色槽
        frame[150:164, 360:460] = green  # 动态条可出现在任意位置
        frame[150:164, 100:280] = green  # 更宽但没有进度槽的普通绿色 UI

        sample = FishingEngine.find_stamina_bar(frame)

        self.assertIsNotNone(sample)
        self.assertEqual(sample.fill_width, 100)  # type: ignore[union-attr]
        self.assertEqual(sample.center, (411, 158))  # type: ignore[union-attr]

    def test_mode_one_uses_physical_up_scroll_in_screen_mode(self) -> None:
        config = AppConfig(catch_strategy="stamina_bounce", stamina_zoom_in_steps=5)
        engine = FishingEngine()
        target = WindowInfo(100, "瑪奇 Mobile", 0, 0, 1920, 1080)
        with patch("fishing_assistant.engine.pyautogui.scroll") as scroll, patch(
            "fishing_assistant.engine.window_target.list_target_windows", return_value=[target]
        ), patch("fishing_assistant.engine.window_target.activate_window") as activate, patch(
            "fishing_assistant.engine.time.sleep"
        ):
            engine._prepare_stamina_view(config)
        scroll.assert_called_once_with(5)
        activate.assert_called_once_with(target.handle)
    def test_mode_one_zooms_target_window_in_background_mode(self) -> None:
        target = WindowInfo(100, "瑪奇 Mobile", 0, 0, 1920, 1080)
        config = AppConfig(
            catch_strategy="stamina_bounce",
            stamina_zoom_in_steps=5,
            capture_mode="window",
            target_window_handle=target.handle,
            target_window_title=target.title,
            target_button_offset=(1600, 860),
        )
        engine = FishingEngine()
        with patch.object(engine, "_resolve_target_window", return_value=target), patch(
            "fishing_assistant.engine.window_target.activate_window"
        ) as activate, patch("fishing_assistant.engine.pyautogui.scroll") as scroll, patch(
            "fishing_assistant.engine.time.sleep"
        ):
            engine._prepare_stamina_view(config)
        activate.assert_called_once_with(target.handle)
        scroll.assert_called_once_with(5)
    def test_f7_recalibration_while_running_rearms_cast(self) -> None:
        config = AppConfig(button_center=(1700, 900))
        engine = FishingEngine()
        engine._config = config  # type: ignore[attr-defined]
        engine._enabled.set()  # type: ignore[attr-defined]

        with patch(
            "fishing_assistant.engine.pyautogui.position",
            return_value=(1710, 920),
        ), patch("fishing_assistant.engine.save_config"), patch.object(
            engine, "_schedule_recast"
        ) as schedule:
            engine.calibrate_from_cursor()

        engine._enabled.clear()  # type: ignore[attr-defined]
        schedule.assert_called_once()
        self.assertEqual(schedule.call_args.args[2], "重新校准完成")

    def test_f7_calibration_records_cursor_without_moving_it(self) -> None:
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.position", return_value=(1700, 910)), patch(
            "fishing_assistant.engine.pyautogui.moveTo"
        ) as move, patch("fishing_assistant.engine.save_config"):
            position = engine.calibrate_from_cursor()
        self.assertEqual(position, (1700, 910))
        self.assertEqual(engine.config().button_center, (1700, 910))
        move.assert_not_called()

    def test_stamina_detector_tracks_bar_after_it_moves_across_the_frame(self) -> None:
        first_hsv = np.zeros((360, 640, 3), dtype=np.uint8)
        first_hsv[50:64, 80:212] = (62, 210, 230)
        moved_hsv = np.zeros((360, 640, 3), dtype=np.uint8)
        moved_hsv[260:274, 430:548] = (62, 210, 230)

        first = FishingEngine.find_stamina_bar(cv2.cvtColor(first_hsv, cv2.COLOR_HSV2BGR))
        moved = FishingEngine.find_stamina_bar(cv2.cvtColor(moved_hsv, cv2.COLOR_HSV2BGR))

        self.assertEqual(first.fill_width, 132)  # type: ignore[union-attr]
        self.assertEqual(moved.fill_width, 118)  # type: ignore[union-attr]
        self.assertGreater(moved.center[0], first.center[0])  # type: ignore[union-attr]
    def test_idle_pointer_runs_ws_then_recasts(self) -> None:
        config = AppConfig(
            recovery_consecutive_frames=1,
            recovery_cooldown_ms=0,
            recovery_pause_ms=0,
            press_cooldown_ms=0,
            recast_delay_ms=650,
        )
        engine = FishingEngine()
        with patch.object(engine, "_tap_key") as tap_key, patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            engine._process_frame(365, config, IconState.IDLE_RECOVERY)
            engine._process_frame(766, config, IconState.READY_TO_CAST)
        self.assertEqual([call.args[0] for call in tap_key.call_args_list], ["w", "s"])
        press.assert_called_once_with("space")

    def test_capture_region_centers_on_calibration_point(self) -> None:
        region = FishingEngine._capture_region(
            AppConfig(button_center=(1800, 960), roi_width=160, roi_height=180)
        )
        self.assertEqual(region, {"left": 1720, "top": 870, "width": 160, "height": 180})

    def test_screen_capture_region_uses_selected_4k_resolution(self) -> None:
        region = FishingEngine._capture_region(
            AppConfig(
                button_center=(3600, 1920),
                selected_resolution="3840 × 2160",
            )
        )
        self.assertEqual(
            region,
            {"left": 3440, "top": 1740, "width": 320, "height": 360},
        )


if __name__ == "__main__":
    unittest.main()
