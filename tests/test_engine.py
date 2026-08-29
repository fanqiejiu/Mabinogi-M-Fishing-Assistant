import unittest
from unittest.mock import patch

import numpy as np

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import FishingEngine


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

    def test_fish_is_collected_then_recast_automatically(self) -> None:
        config = AppConfig(
            trigger_consecutive_frames=1,
            clear_consecutive_frames=1,
            press_cooldown_ms=0,
            recast_delay_ms=0,
        )
        engine = FishingEngine()
        with patch("fishing_assistant.engine.pyautogui.press") as press:
            engine._process_frame(1985, config)
            engine._process_frame(0, config)
        self.assertEqual(press.call_args_list[0].args, ("space",))
        self.assertEqual(press.call_args_list[1].args, ("space",))

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
