"""背包自动整理的识别、安全门与流程回归测试。"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from pynput import keyboard

from fishing_assistant.config import AppConfig
from fishing_assistant.constants import (
    CLEANUP_DETAIL_HEADER_PATH,
    CLEANUP_RESULT_HEADER_PATH,
)
from fishing_assistant.engine import EventKind, FishingEngine
from fishing_assistant.inventory_cleanup import (
    BoldCleanupState,
    InventoryCleanupVision,
    SimpleCleanupState,
    TemplateMatch,
)


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _panel_frame(path: Path, width: int, height: int, ui_scale: float) -> np.ndarray:
    panel = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if ui_scale != 1.0:
        panel = cv2.resize(
            panel,
            (
                round(panel.shape[1] * ui_scale),
                round(panel.shape[0] * ui_scale),
            ),
            interpolation=cv2.INTER_AREA,
        )
    frame = np.full((height, width, 3), 35, dtype=np.uint8)
    left = (width - panel.shape[1]) // 2
    top = (height - panel.shape[0]) // 2
    frame[top : top + panel.shape[0], left : left + panel.shape[1]] = panel
    return frame


def _simple_state(
    selected: tuple[bool, bool, bool, bool],
    *,
    bold: BoldCleanupState = BoldCleanupState.OFF,
) -> SimpleCleanupState:
    return SimpleCleanupState(
        anchor=TemplateMatch(640, 170, 220, 65, 0.95, 1.0),
        bold_cleanup=bold,
        selected_categories=selected,
        execute_enabled=any(selected),
        category_green_ratios=tuple(0.10 if value else 0.0 for value in selected),
        execute_green_ratio=0.78 if any(selected) else 0.0,
    )


class InventoryCleanupVisionTests(unittest.TestCase):
    def setUp(self) -> None:
        InventoryCleanupVision._feature_set = None
        InventoryCleanupVision._templates = {}

    def test_bold_cleanup_on_and_off_are_distinguished(self) -> None:
        on_frame = _panel_frame(
            FIXTURES / "cleanup_simple_on.png", 1920, 1080, 1.0
        )
        off_frame = _panel_frame(
            FIXTURES / "cleanup_simple_off.png", 1920, 1080, 1.0
        )

        on_state = InventoryCleanupVision.inspect_simple_screen(on_frame)
        off_state = InventoryCleanupVision.inspect_simple_screen(off_frame)

        self.assertIsNotNone(on_state)
        self.assertIsNotNone(off_state)
        self.assertEqual(on_state.bold_cleanup, BoldCleanupState.ON)
        self.assertEqual(off_state.bold_cleanup, BoldCleanupState.OFF)
        self.assertEqual(
            off_state.selected_categories,
            (True, False, False, False),
        )
        self.assertTrue(off_state.execute_enabled)

    def test_simple_screen_scales_for_2k_4k_and_16_by_10(self) -> None:
        cases = (
            (2560, 1440, 4 / 3),
            (3840, 2160, 2.0),
            (2560, 1600, 4 / 3),
        )
        for width, height, ui_scale in cases:
            with self.subTest(size=(width, height)):
                frame = _panel_frame(
                    FIXTURES / "cleanup_simple_off.png",
                    width,
                    height,
                    ui_scale,
                )
                state = InventoryCleanupVision.inspect_simple_screen(frame)
                self.assertIsNotNone(state)
                self.assertEqual(state.bold_cleanup, BoldCleanupState.OFF)
                self.assertTrue(state.selected_categories[0])

    def test_similar_detail_and_result_headings_do_not_cross_match(self) -> None:
        detail = cv2.imread(str(CLEANUP_DETAIL_HEADER_PATH), cv2.IMREAD_COLOR)
        result = cv2.imread(str(CLEANUP_RESULT_HEADER_PATH), cv2.IMREAD_COLOR)
        detail_frame = np.full((1080, 1920, 3), 35, dtype=np.uint8)
        result_frame = detail_frame.copy()
        detail_frame[260 : 260 + detail.shape[0], 830 : 830 + detail.shape[1]] = detail
        result_frame[245 : 245 + result.shape[0], 830 : 830 + result.shape[1]] = result

        self.assertIsNotNone(InventoryCleanupVision.find_detail(detail_frame))
        self.assertIsNone(InventoryCleanupVision.find_result(detail_frame))
        self.assertIsNotNone(InventoryCleanupVision.find_result(result_frame))
        self.assertIsNone(InventoryCleanupVision.find_detail(result_frame))


class InventoryCleanupFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.events = []
        self.engine = FishingEngine(self.events.append)
        self.engine._enabled.set()  # type: ignore[attr-defined]
        self.config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_window_handle=101,
            target_window_title="瑪奇 Mobile",
            target_button_offset=(1700, 900),
            inventory_auto_cleanup_enabled=True,
        )
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.match = TemplateMatch(1700, 760, 130, 82, 0.96, 1.0)

    def test_full_safe_flow_selects_four_categories_then_resumes(self) -> None:
        initial_on = _simple_state(
            (False, False, False, False),
            bold=BoldCleanupState.ON,
        )
        safe_empty = _simple_state((False, False, False, False))
        progressive = (
            _simple_state((True, False, False, False)),
            _simple_state((True, True, False, False)),
            _simple_state((True, True, True, False)),
            _simple_state((True, True, True, True)),
        )
        safe_ready = progressive[-1]
        wait_results = (
            (self.frame, self.match),
            (self.frame, initial_on),
            (self.frame, self.match),
            (self.frame, self.match),
            (self.frame, self.match),
        )

        with (
            patch.object(
                self.engine,
                "_wait_cleanup_screen",
                side_effect=wait_results,
            ),
            patch.object(
                self.engine,
                "_confirm_simple_cleanup_safety",
                side_effect=(safe_empty, safe_ready, safe_ready),
            ),
            patch.object(
                self.engine,
                "_capture_stamina_frame",
                return_value=self.frame,
            ),
            patch.object(
                InventoryCleanupVision,
                "inspect_simple_screen",
                side_effect=progressive,
            ),
            patch.object(self.engine, "_click_game_point") as click,
            patch.object(self.engine, "_press_key") as press_key,
            patch.object(self.engine, "_restore_fishing_pointer"),
            patch.object(self.engine, "_schedule_recast") as schedule,
            patch("fishing_assistant.engine.time.sleep"),
        ):
            handled = self.engine._perform_inventory_cleanup(  # type: ignore[attr-defined]
                self.config, 0.93
            )

        self.assertTrue(handled)
        self.assertTrue(self.engine.is_monitoring())
        self.assertEqual([call.args[0] for call in press_key.call_args_list], ["i", "esc"])
        self.assertEqual(click.call_count, 9)
        schedule.assert_called_once()
        self.assertTrue(
            any(event.kind == EventKind.SUCCESS for event in self.events)
        )

    def test_uncertain_bold_switch_stops_before_destructive_buttons(self) -> None:
        initial_on = _simple_state(
            (False, False, False, False),
            bold=BoldCleanupState.ON,
        )
        with (
            patch.object(
                self.engine,
                "_wait_cleanup_screen",
                side_effect=(
                    (self.frame, self.match),
                    (self.frame, initial_on),
                ),
            ),
            patch.object(
                self.engine,
                "_confirm_simple_cleanup_safety",
                side_effect=RuntimeError("未确认大胆整理关闭"),
            ),
            patch.object(self.engine, "_click_game_point") as click,
            patch.object(self.engine, "_press_key"),
            patch("fishing_assistant.engine.time.sleep"),
        ):
            handled = self.engine._perform_inventory_cleanup(  # type: ignore[attr-defined]
                self.config, 0.93
            )

        self.assertTrue(handled)
        self.assertFalse(self.engine.is_monitoring())
        # 只允许点背包里的“整理”和大胆整理开关，未进入任何真正整理按钮。
        self.assertEqual(click.call_count, 2)
        errors = [event for event in self.events if event.kind == EventKind.ERROR]
        self.assertEqual(len(errors), 1)
        self.assertIn("没有继续执行后续整理点击", errors[0].message)

    def test_debug_request_requires_enabled_feature_and_calibration(self) -> None:
        self.engine._enabled.clear()  # type: ignore[attr-defined]
        self.engine._config = AppConfig()  # type: ignore[attr-defined]
        self.assertFalse(self.engine.request_inventory_cleanup_test())

        self.engine._config = AppConfig(  # type: ignore[attr-defined]
            inventory_auto_cleanup_enabled=True,
        )
        self.assertFalse(self.engine.request_inventory_cleanup_test())

        self.engine._config = AppConfig(  # type: ignore[attr-defined]
            capture_mode="screen",
            button_center=(1700, 900),
            inventory_auto_cleanup_enabled=True,
        )
        self.assertTrue(self.engine.request_inventory_cleanup_test())
        self.assertTrue(self.engine.is_monitoring())
        self.assertTrue(
            self.engine._cleanup_test_requested.is_set()  # type: ignore[attr-defined]
        )

    @patch("fishing_assistant.engine.pyautogui.press")
    def test_synthetic_screen_esc_does_not_trigger_emergency_stop(
        self, press
    ) -> None:
        config = AppConfig(capture_mode="screen", button_center=(1700, 900))
        self.engine._enabled.set()  # type: ignore[attr-defined]
        with patch("fishing_assistant.engine.time.monotonic", return_value=100.0):
            self.engine._press_key("esc", config)  # type: ignore[attr-defined]
        press.assert_called_once_with("esc")

        with patch("fishing_assistant.engine.time.monotonic", return_value=100.2):
            self.engine._on_key_press(keyboard.Key.esc)  # type: ignore[attr-defined]
        self.assertTrue(self.engine.is_monitoring())


if __name__ == "__main__":
    unittest.main()
