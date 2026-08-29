import unittest
from unittest.mock import patch

import cv2
import numpy as np

from fishing_assistant.config import AppConfig
from fishing_assistant.constants import FISH_ESCAPE_TEMPLATE_PATH
from fishing_assistant.engine import FishingEngine, IconState, StaminaBarSample
from fishing_assistant.window_target import WindowInfo


class FishingEngineTests(unittest.TestCase):
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
            FishingEngine.classify_icon_state(766, config).value, "normal"
        )
        self.assertEqual(
            FishingEngine.classify_icon_state(365, config).value, "idle_recovery"
        )
        self.assertEqual(
            FishingEngine.classify_icon_state(1985, config).value, "fish_hooked"
        )

    def test_horse_icons_override_fishing_states(self) -> None:
        def horse_frame(with_dismount_arrow: bool) -> np.ndarray:
            hsv = np.zeros((180, 160, 3), dtype=np.uint8)
            hsv[:, :] = (60, 170, 220)
            hsv[48:102, 48:98] = (0, 0, 245)
            hsv[76:94, 76:98] = (16, 180, 155)
            if with_dismount_arrow:
                hsv[112:130, 68:92] = (0, 220, 240)
            return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        mount_state, _ = FishingEngine.classify_frame_state(horse_frame(False), AppConfig())
        dismount_state, _ = FishingEngine.classify_frame_state(horse_frame(True), AppConfig())
        self.assertEqual(mount_state, IconState.HORSE_MOUNT_PROMPT)
        self.assertEqual(dismount_state, IconState.HORSE_DISMOUNT_PROMPT)

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
            engine._process_frame(1985, config)
            engine._process_frame(1985, config)
            engine._process_frame(0, config)
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
            engine._process_frame(1985, config)
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
        with patch("fishing_assistant.engine.pyautogui.press") as press:
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
            engine._process_frame(1985, config, stamina_sample=peak)
            engine._process_frame(1985, config, stamina_sample=trough)
            press.assert_not_called()
            engine._process_frame(1985, config, stamina_sample=rebound)
        press.assert_called_once_with("space")

    def test_tracking_that_starts_below_half_does_not_guess_first_crossing(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(55, (80, 80)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(45, (500, 320)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(132, (500, 320)))
        press.assert_not_called()
    def test_stamina_bar_without_rebound_is_not_collected(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(132, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(48, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(56, (400, 300)))
        press.assert_not_called()

    def test_stamina_rebound_works_when_first_peak_is_seen_late(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(80, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(38, (560, 480)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(57, (120, 720)))
        press.assert_called_once_with("space")

    def test_first_half_crossing_and_small_jitter_do_not_collect(self) -> None:
        config = AppConfig(
            catch_strategy="stamina_bounce",
            trigger_consecutive_frames=1,
            press_cooldown_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(132, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(64, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(65, (400, 300)))
            press.assert_not_called()
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(46, (400, 300)))
            engine._process_frame(1985, config, stamina_sample=StaminaBarSample(72, (400, 300)))
        press.assert_called_once_with("space")

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
            recast_delay_ms=0,
        )
        engine = FishingEngine()
        with patch.object(engine, "_tap_key") as tap_key, patch(
            "fishing_assistant.engine.pyautogui.press"
        ) as press:
            engine._process_frame(365, config)
            engine._process_frame(0, config)
        self.assertEqual([call.args[0] for call in tap_key.call_args_list], ["w", "s"])
        press.assert_called_once_with("space")

    def test_capture_region_centers_on_calibration_point(self) -> None:
        region = FishingEngine._capture_region(
            AppConfig(button_center=(1800, 960), roi_width=160, roi_height=180)
        )
        self.assertEqual(region, {"left": 1720, "top": 870, "width": 160, "height": 180})


if __name__ == "__main__":
    unittest.main()
