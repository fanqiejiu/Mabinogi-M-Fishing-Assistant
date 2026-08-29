from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import EventKind, FishingEngine
from fishing_assistant.window_target import WindowInfo


class WindowModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = []
        self.engine = FishingEngine(self.events.append)
        self.target = WindowInfo(101, "洛奇 M", 100, 200, 1920, 1080)

    def test_window_mode_requires_window_relative_calibration(self) -> None:
        self.engine._config = AppConfig(  # type: ignore[attr-defined]
            capture_mode="window",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
        )

        self.assertFalse(self.engine.set_monitoring(True))
        self.assertEqual(self.events[-1].kind, EventKind.WARNING)
        self.assertIn("选择目标窗口", self.events[-1].message)

    @patch("fishing_assistant.engine.pyautogui.press")
    @patch("fishing_assistant.engine.window_target.post_key_tap")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_mode_never_uses_foreground_pyautogui_press(
        self, resolve_window, post_key_tap, foreground_press
    ) -> None:
        resolve_window.return_value = self.target
        config = AppConfig(
            capture_mode="window",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        self.engine._press_key("space", config)  # type: ignore[attr-defined]

        post_key_tap.assert_called_once_with(self.target.handle, "space")
        foreground_press.assert_not_called()

    @patch("fishing_assistant.engine.window_target.capture_window_region")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_capture_uses_window_relative_button_offset(
        self, resolve_window, capture_window_region
    ) -> None:
        resolve_window.return_value = self.target
        expected = np.zeros((180, 160, 4), dtype=np.uint8)
        capture_window_region.return_value = expected
        config = AppConfig(
            capture_mode="window",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        frame = self.engine._capture_frame(None, config)  # type: ignore[attr-defined]

        self.assertIs(frame, expected)
        capture_window_region.assert_called_once_with(
            self.target.handle, (1600, 860), 160, 180
        )


if __name__ == "__main__":
    unittest.main()
