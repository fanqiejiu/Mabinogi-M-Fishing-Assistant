"""启停边界回归：全部使用假画面和假输入，不操作真实游戏。"""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from pynput import keyboard

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import (
    EngineEvent, EventKind, FishingEngine, IconState, _OperationCancelled,
)
from fishing_assistant.inventory_cleanup import (
    BoldCleanupState, InventoryCleanupVision, SimpleCleanupState, TemplateMatch,
)
from fishing_assistant.ui import MainWindow
from fishing_assistant.voice_alerts import (
    CRITICAL_STOP_CUE, RECOGNITION_FAILED_CUE, cue_for_engine_event,
)


class SessionSafetyTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.engine = FishingEngine(self.events.append)
        self.config = AppConfig(
            capture_mode="window", target_button_offset=(1700, 900),
            catch_strategy="instant", poll_interval_ms=0,
            runtime_error_retry_count=0,
        )
        self.engine._config = self.config
        self.engine._enabled.set()
        self.frame = np.zeros((180, 160, 3), dtype=np.uint8)

    def test_held_hotkeys_only_fire_once_until_released(self):
        for key, method in (
            (keyboard.Key.f7, "calibrate_from_cursor"),
            (keyboard.Key.f8, "toggle_monitoring"),
            (keyboard.Key.f9, "request_debug_capture"),
        ):
            with self.subTest(key=key), patch.object(self.engine, method) as action:
                for _ in range(5):
                    self.engine._on_key_press(key)
                action.assert_called_once()
                self.engine._on_key_release(key)
                self.engine._on_key_press(key)
                self.assertEqual(action.call_count, 2)
                self.engine._on_key_release(key)

    def test_pause_clears_enabled_before_resetting_detection(self):
        seen = []
        with patch.object(
            self.engine, "_reset_detection",
            side_effect=lambda: seen.append(self.engine.is_monitoring()),
        ):
            self.engine.set_monitoring(False)
        self.assertEqual(seen, [False])

    def test_capture_completed_after_pause_is_not_processed_or_reported(self):
        for restart in (False, True):
            for failure in (False, True):
                with self.subTest(restart=restart, failure=failure):
                    self.engine._shutdown.clear()
                    self.engine._enabled.set()
                    self.events.clear()

                    def capture(*_args):
                        self.engine.set_monitoring(False)
                        if restart:
                            self.engine._enabled.set()
                        if failure:
                            raise RuntimeError("old capture failed")
                        return self.frame

                    waits = 0

                    def wait(**_kwargs):
                        nonlocal waits
                        waits += 1
                        if waits == 1:
                            return True
                        self.engine._shutdown.set()
                        return False

                    with (
                        patch.object(self.engine._enabled, "wait", side_effect=wait),
                        patch.object(self.engine, "_capture_frame", side_effect=capture),
                        patch.object(self.engine, "classify_frame_state") as classify,
                        patch.object(self.engine, "_process_frame") as process,
                        patch.object(self.engine, "_close_ok_window_backend") as close,
                    ):
                        self.engine._monitor_loop()
                    classify.assert_not_called()
                    process.assert_not_called()
                    close.assert_not_called()
                    self.assertEqual(self.engine.is_monitoring(), restart)
                    self.assertFalse(any(e.kind == EventKind.ERROR for e in self.events))

    def test_pause_during_virtual_hover_prevents_space(self):
        self.engine._work_context.generation = self.engine._interrupt_generation
        backend = MagicMock()
        with (
            patch.object(self.engine, "_resolve_target_window"),
            patch.object(self.engine, "_maintain_background_hover",
                         side_effect=lambda *_a, **_kw: self.engine.set_monitoring(False)),
            patch.object(self.engine, "_get_ok_window_backend", return_value=backend),
        ):
            with self.assertRaises(_OperationCancelled):
                self.engine._press_key("space", self.config)
        backend.tap_key.assert_not_called()

    def test_pause_and_restart_during_backend_setup_prevents_click(self):
        self.engine._work_context.generation = self.engine._interrupt_generation
        backend = MagicMock()

        def get_backend(*_args):
            self.engine.set_monitoring(False)
            self.engine._enabled.set()
            return backend

        with (
            patch.object(self.engine, "_resolve_target_window"),
            patch.object(self.engine, "_get_ok_window_backend", side_effect=get_backend),
        ):
            with self.assertRaises(_OperationCancelled):
                self.engine._click_game_point((100, 100), self.config, None)
        backend.click.assert_not_called()

    def test_emitted_error_includes_actual_monitoring_status(self):
        with patch("fishing_assistant.engine.record_error"):
            self.engine._emit(EventKind.ERROR, "保存识别区域失败")
        self.assertTrue(self.events[-1].monitoring)
        self.assertEqual(cue_for_engine_event("error", "保存失败", True),
                         RECOGNITION_FAILED_CUE)
        self.assertEqual(cue_for_engine_event("error", "识别已停止", False),
                         CRITICAL_STOP_CUE)

    def test_pause_during_startup_does_not_enable_monitoring_afterwards(self):
        self.engine._enabled.clear()
        with (
            patch.object(self.engine, "_resolve_target_window"),
            patch.object(self.engine, "_maintain_background_hover") as hover,
            patch.object(self.engine, "_prepare_stamina_view",
                         side_effect=lambda *_a: self.engine.set_monitoring(False)),
        ):
            self.assertFalse(self.engine.set_monitoring(True))
        self.assertFalse(self.engine.is_monitoring())
        hover.assert_not_called()

    def test_auxiliary_scans_do_not_report_pause_as_recognition_failure(self):
        for method in (
            "_capture_stamina_sample", "_capture_escape_message_confidence",
            "_capture_blocking_message_confidences",
        ):
            with self.subTest(method=method):
                self.engine._enabled.set()
                self.engine._work_context.generation = self.engine._interrupt_generation
                self.events.clear()

                def capture(*_args):
                    self.engine.set_monitoring(False)
                    raise RuntimeError("late capture failure")

                with patch.object(self.engine, "_capture_stamina_frame", side_effect=capture):
                    with self.assertRaises(_OperationCancelled):
                        getattr(self.engine, method)(None, self.config, 100.0)
                self.assertFalse(any(e.kind == EventKind.WARNING for e in self.events))


class CleanupCancellationTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.engine = FishingEngine(self.events.append)
        self.engine._enabled.set()
        self.config = AppConfig(capture_mode="window", target_button_offset=(1700, 900))
        self.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.match = TemplateMatch(640, 170, 220, 65, 0.95, 1.0)
        self.safe = SimpleCleanupState(
            self.match, BoldCleanupState.OFF, (True, True, True, True),
            True, (0.1, 0.1, 0.1, 0.1), 0.78,
        )

    def test_pause_after_final_safety_check_prevents_execute_click(self):
        checks = 0

        def confirm(*_args, **_kwargs):
            nonlocal checks
            checks += 1
            if checks == 3:
                self.engine.set_monitoring(False)
                self.engine._enabled.set()  # 即使立即重启也不能沿用旧清理步骤。
            return self.safe

        with (
            patch.object(self.engine, "_wait_cleanup_screen", side_effect=[
                (self.frame, self.match), (self.frame, self.safe),
            ]),
            patch.object(self.engine, "_confirm_simple_cleanup_safety", side_effect=confirm),
            patch.object(self.engine, "_click_game_point") as click,
            patch.object(self.engine, "_press_key"),
        ):
            self.engine._perform_inventory_cleanup(self.config, 1.0)
        self.assertEqual(checks, 3)
        click.assert_called_once_with(self.match.center, self.config, None)
        self.assertTrue(self.engine.is_monitoring())
        self.assertFalse(any(e.kind == EventKind.ERROR for e in self.events))

    def test_detector_result_after_pause_is_discarded(self):
        generation = self.engine._interrupt_generation

        def detect(_frame):
            self.engine.set_monitoring(False)
            return self.match

        with patch.object(self.engine, "_capture_stamina_frame", return_value=self.frame):
            with self.assertRaises(_OperationCancelled):
                self.engine._wait_cleanup_screen(None, self.config, generation, detect, "测试")

    def test_cleanup_error_after_restart_does_not_stop_new_session(self):
        def wait(*_args):
            self.engine.set_monitoring(False)
            self.engine._enabled.set()
            raise RuntimeError("old cleanup capture failed")

        with (
            patch.object(self.engine, "_wait_cleanup_screen", side_effect=wait),
            patch.object(self.engine, "_press_key"),
        ):
            self.engine._perform_inventory_cleanup(self.config, 1.0)
        self.assertTrue(self.engine.is_monitoring())
        self.assertFalse(any(e.kind == EventKind.ERROR for e in self.events))


class UiSessionSafetyTests(unittest.TestCase):
    def test_late_metric_cannot_override_paused_state(self):
        owner = MagicMock()
        owner.engine.is_monitoring.return_value = False
        MainWindow._consume_engine_event(owner, EngineEvent(
            kind=EventKind.METRIC, message="等待上钩", monitoring=True,
            icon_state=IconState.WAITING_BITE,
        ))
        owner._set_runtime_state.assert_not_called()
        owner.runtime_detail.setText.assert_not_called()

    def test_cleanup_debug_has_cleanup_state_not_fishing_state(self):
        owner = MagicMock()
        owner.engine.is_monitoring.return_value = True
        MainWindow._consume_engine_event(owner, EngineEvent(
            kind=EventKind.STATE, message="背包清理调试：正在准备", monitoring=True,
        ))
        owner._set_runtime_state.assert_called_with("清理背包", "running")
        owner.runtime_detail.setText.assert_called_with("背包清理调试：正在准备")

    def test_auxiliary_error_does_not_show_fishing_as_stopped(self):
        owner = MagicMock()
        owner.engine.is_monitoring.return_value = True
        MainWindow._consume_engine_event(owner, EngineEvent(
            kind=EventKind.ERROR, message="保存识别区域失败", monitoring=True,
        ))
        owner.start_button.setText.assert_not_called()
        owner.runtime_title.setText.assert_not_called()
        owner.voice_player.play.assert_called_once_with(RECOGNITION_FAILED_CUE)

    def test_update_worker_reports_unexpected_error_to_restore_button(self):
        owner = MagicMock()

        def thread(**kwargs):
            worker = MagicMock()
            worker.start.side_effect = kwargs["target"]
            return worker

        with (
            patch("fishing_assistant.ui.threading.Thread", side_effect=thread),
            patch("fishing_assistant.ui.check_github_release", side_effect=ValueError("bad data")),
            patch("fishing_assistant.ui.record_error"),
        ):
            MainWindow._check_for_updates(owner, manual=True)
        result = owner.update_ready.emit.call_args.args[0]
        self.assertFalse(result.ok)
        MainWindow._show_update_result(owner, result)
        owner.check_update_button.setEnabled.assert_called_with(True)


if __name__ == "__main__":
    unittest.main()
