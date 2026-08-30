from __future__ import annotations

import unittest
from unittest.mock import MagicMock, call, patch

import numpy as np

from fishing_assistant import window_target
from fishing_assistant.config import AppConfig
from fishing_assistant.engine import EventKind, FishingEngine, IconState
from fishing_assistant.window_target import WindowInfo, find_mabinogi_mobile_window


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

    def test_prefers_exact_mabinogi_mobile_window_title(self) -> None:
        fallback = WindowInfo(1, "其他游戏", 0, 0, 800, 600)
        partial = WindowInfo(2, "瑪奇 Mobile - 登录中", 0, 0, 800, 600)
        exact = WindowInfo(3, "瑪奇 Mobile", 0, 0, 800, 600)

        self.assertEqual(find_mabinogi_mobile_window([fallback, partial, exact]), exact)
        self.assertIsNone(find_mabinogi_mobile_window([fallback]))

    @patch("fishing_assistant.engine.pyautogui.press")
    @patch("fishing_assistant.engine.window_target.post_key_tap")
    @patch("fishing_assistant.engine.window_target.post_mouse_move")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_mode_never_uses_foreground_pyautogui_press(
        self, resolve_window, post_mouse_move, post_key_tap, foreground_press
    ) -> None:
        resolve_window.return_value = self.target
        config = AppConfig(
            capture_mode="window",
            window_backend="printwindow",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        self.engine._press_key("space", config)  # type: ignore[attr-defined]

        post_mouse_move.assert_called_once_with(self.target.handle, (1600, 860))
        post_key_tap.assert_called_once_with(
            self.target.handle, "space", activate_message=True
        )
        foreground_press.assert_not_called()

    @patch("fishing_assistant.engine.window_target.capture_window_region")
    @patch("fishing_assistant.engine.window_target.post_mouse_move")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_capture_uses_window_relative_button_offset(
        self, resolve_window, post_mouse_move, capture_window_region
    ) -> None:
        resolve_window.return_value = self.target
        expected = np.zeros((180, 160, 4), dtype=np.uint8)
        capture_window_region.return_value = expected
        config = AppConfig(
            capture_mode="window",
            window_backend="printwindow",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        frame = self.engine._capture_frame(None, config)  # type: ignore[attr-defined]

        self.assertIs(frame, expected)
        post_mouse_move.assert_called_once_with(self.target.handle, (1600, 860))
        capture_window_region.assert_called_once_with(
            self.target.handle, (1600, 860), 160, 180
        )

    @patch("fishing_assistant.engine.window_target.capture_window_region")
    @patch("fishing_assistant.engine.window_target.post_mouse_move")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_capture_auto_scales_roi_for_2k_target(
        self, resolve_window, post_mouse_move, capture_window_region
    ) -> None:
        target = WindowInfo(202, "瑪奇 Mobile", 100, 200, 2560, 1440)
        resolve_window.return_value = target
        expected = np.zeros((240, 214, 4), dtype=np.uint8)
        capture_window_region.return_value = expected
        config = AppConfig(
            capture_mode="window",
            window_backend="printwindow",
            target_window_handle=target.handle,
            target_window_title=target.title,
            target_button_offset=(2200, 1200),
        )

        frame = self.engine._capture_frame(None, config)  # type: ignore[attr-defined]

        self.assertIs(frame, expected)
        capture_window_region.assert_called_once_with(
            target.handle, (2200, 1200), 214, 240
        )

    @patch("fishing_assistant.engine.time.sleep")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_ws_recovery_refreshes_virtual_hover_before_space(
        self, resolve_window, sleep
    ) -> None:
        resolve_window.return_value = self.target
        backend = MagicMock()
        backend.handle = self.target.handle
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
            recovery_pause_ms=0,
        )
        self.engine._config = config  # type: ignore[attr-defined]
        self.engine._pending_recast_at = 1.0  # type: ignore[attr-defined]
        self.engine._pending_recast_reason = "启动指南针移动恢复完成"  # type: ignore[attr-defined]

        with patch.object(
            self.engine, "_get_ok_window_backend", return_value=backend
        ), patch.object(self.engine, "_tap_key") as tap_key:
            self.engine._recover_idle_state(config, startup=True)  # type: ignore[attr-defined]
            self.assertTrue(
                self.engine._refresh_hover_before_recast  # type: ignore[attr-defined]
            )
            self.engine._perform_pending_recast(2.0, IconState.READY_TO_CAST, config)  # type: ignore[attr-defined]

        self.assertEqual(
            [item.args[0] for item in tap_key.call_args_list],
            ["w", "s"],
        )
        self.assertEqual(
            backend.mock_calls,
            [
                call.keep_hover(self.target, (960, 540)),
                call.keep_hover(self.target, (1600, 860)),
                call.keep_hover(self.target, (1600, 860)),
                call.tap_key("space"),
            ],
        )
        self.assertEqual(sleep.call_count, 3)
        self.assertFalse(
            self.engine._refresh_hover_before_recast  # type: ignore[attr-defined]
        )

    @patch("fishing_assistant.engine.window_target.capture_window_frame")
    @patch("fishing_assistant.engine.window_target.post_mouse_move")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_window_stamina_capture_uses_full_target_frame(
        self, resolve_window, post_mouse_move, capture_window_frame
    ) -> None:
        resolve_window.return_value = self.target
        expected = np.zeros((1080, 1920, 4), dtype=np.uint8)
        capture_window_frame.return_value = expected
        config = AppConfig(
            capture_mode="window",
            window_backend="printwindow",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        frame = self.engine._capture_stamina_frame(None, config)  # type: ignore[attr-defined]

        self.assertIs(frame, expected)
        post_mouse_move.assert_called_once_with(self.target.handle, (1600, 860))
        capture_window_frame.assert_called_once_with(self.target.handle)

    def test_ok_window_backend_retries_empty_startup_frames(self) -> None:
        backend = window_target.OkWindowBackend(self.target)
        first = None
        expected = np.zeros((1080, 1920, 3), dtype=np.uint8)
        backend._capture = type("Capture", (), {"get_frame": lambda _self: first})()  # type: ignore[attr-defined]
        with patch("fishing_assistant.window_target.time.sleep"), patch.object(
            backend._capture, "get_frame", side_effect=[None, expected]
        ):
            frame = backend._get_frame_with_warmup()  # type: ignore[attr-defined]
        self.assertIs(frame, expected)

    def test_ok_crop_shifts_bottom_right_roi_inside_wgc_frame(self) -> None:
        info = WindowInfo(101, "瑪奇 Mobile", 0, 0, 1918, 1030)
        frame = np.zeros((1030, 1918, 3), dtype=np.uint8)
        frame[950, 1821] = (11, 22, 33)

        cropped = window_target._crop_backend_frame(
            frame, info, (1821, 950), 160, 186
        )

        self.assertEqual(cropped.shape, (186, 160, 3))
        np.testing.assert_array_equal(cropped[106, 80], (11, 22, 33))

    def test_ok_window_backend_virtual_hover_uses_message_only(self) -> None:
        backend = window_target.OkWindowBackend(self.target)
        backend._capture = object()  # type: ignore[attr-defined]
        backend._interaction = MagicMock()  # type: ignore[attr-defined]

        backend.keep_hover(self.target, (1600, 860))

        backend._interaction.move.assert_called_once_with(1600, 860)  # type: ignore[attr-defined]
    @patch("fishing_assistant.engine.window_target.OkWindowBackend")
    @patch("fishing_assistant.engine.window_target.resolve_window")
    def test_ok_window_backend_handles_capture_and_key(
        self, resolve_window, backend_type
    ) -> None:
        resolve_window.return_value = self.target
        backend = backend_type.return_value
        backend.handle = self.target.handle
        backend.capture_region.return_value = np.zeros((180, 160, 3), dtype=np.uint8)
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_window_handle=self.target.handle,
            target_window_title=self.target.title,
            target_button_offset=(1600, 860),
        )

        self.engine._capture_frame(None, config)  # type: ignore[attr-defined]
        self.engine._press_key("space", config)  # type: ignore[attr-defined]

        backend.capture_region.assert_called_once_with(
            self.target, (1600, 860), 160, 180
        )
        self.assertEqual(backend.keep_hover.call_count, 2)
        backend.keep_hover.assert_any_call(self.target, (1600, 860))
        backend.tap_key.assert_called_once_with("space")


if __name__ == "__main__":
    unittest.main()
