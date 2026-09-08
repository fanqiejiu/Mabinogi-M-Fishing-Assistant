"""F9 异步现场保存：同帧、中文路径、去重和独立界面状态。"""

import json
import threading
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
from pynput import keyboard

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import EngineEvent, EventKind, FishingEngine
from fishing_assistant.ui import MainWindow
from fishing_assistant.window_target import WindowInfo, _crop_backend_frame


class F9CaptureTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.engine = FishingEngine(self.events.append)
        self.config = AppConfig(
            capture_mode="window", target_button_offset=(300, 240),
            auto_scale_roi=False, roi_width=160, roi_height=180,
        )
        self.engine._config = self.config
        self.frame = np.random.default_rng(0).integers(0, 256, (360, 640, 3), dtype=np.uint8)
        self.context = (self.frame, (300, 240), {"expected_size": [640, 360]})

    def test_same_frame_saved_in_timestamped_zip_and_unicode_roi_path(self):
        with (
            TemporaryDirectory() as tmp,
            patch("fishing_assistant.engine.VISION_DIAGNOSTICS_DIR", Path(tmp) / "中文诊断"),
            patch.object(self.engine, "_diagnostic_capture_context", return_value=self.context) as capture,
            patch("fishing_assistant.engine.vision_diagnostics.run_pipeline_check", return_value=None),
            patch("fishing_assistant.engine.vision_diagnostics.collect_environment", return_value={}),
            patch.object(self.engine, "_press_key") as press,
            patch.object(self.engine, "_maintain_background_hover") as hover,
        ):
            first = self.engine.save_debug_capture()
            second = self.engine.save_debug_capture()
            self.assertNotEqual(first, second)
            self.assertEqual(capture.call_count, 2)  # 每次仅截取一次完整画面。
            self.assertTrue(first.is_file())
            expected = self.frame[150:330, 220:380]
            np.testing.assert_array_equal(
                cv2.imdecode(np.frombuffer(first.read_bytes(), np.uint8), cv2.IMREAD_COLOR), expected,
            )
            with zipfile.ZipFile(self.events[-1].diagnostic_path) as bundle:
                self.assertTrue({"roi.png", "frame.png", "report.json"} <= set(bundle.namelist()))
                roi = cv2.imdecode(np.frombuffer(bundle.read("roi.png"), np.uint8), cv2.IMREAD_COLOR)
                np.testing.assert_array_equal(roi, expected)
                full = cv2.imdecode(np.frombuffer(bundle.read("frame.png"), np.uint8), cv2.IMREAD_COLOR)
                np.testing.assert_array_equal(full, self.frame)
            press.assert_not_called()
            hover.assert_not_called()
        self.assertFalse(self.engine.is_monitoring())
        self.assertEqual(self.engine.config(), self.config)
        self.assertEqual(self.events[-1].snapshot_state, "saved")

    def test_scaled_window_roi_matches_actual_ok_backend_crop(self):
        self.config = self.config.copy(target_button_offset=(1250, 700))
        target = WindowInfo(101, "游戏", 0, 0, 1280, 720)
        with (
            TemporaryDirectory() as tmp,
            patch("fishing_assistant.engine.VISION_DIAGNOSTICS_DIR", Path(tmp)),
            patch.object(self.engine, "_diagnostic_capture_context", return_value=(
                self.frame, (1250, 700), {"expected_size": [1280, 720]},
            )),
            patch("fishing_assistant.engine.vision_diagnostics.run_pipeline_check", return_value=None),
            patch("fishing_assistant.engine.vision_diagnostics.collect_environment", return_value={}),
        ):
            path = self.engine.save_debug_capture(self.config)
            self.assertIsNotNone(path)
            actual = cv2.imdecode(np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            expected = _crop_backend_frame(self.frame, target, (1250, 700), 160, 180)
            np.testing.assert_array_equal(actual, expected)

    def test_secondary_monitor_keeps_local_center_for_report(self):
        config = self.config.copy(capture_mode="screen", button_center=(-340, 240))
        with (
            TemporaryDirectory() as tmp,
            patch("fishing_assistant.engine.VISION_DIAGNOSTICS_DIR", Path(tmp)),
            patch.object(self.engine, "_diagnostic_capture_context", return_value=self.context),
            patch("fishing_assistant.engine.vision_diagnostics.run_pipeline_check", return_value=None) as check,
            patch("fishing_assistant.engine.vision_diagnostics.collect_environment", return_value={}),
        ):
            self.engine.save_debug_capture(config)
            self.assertEqual(check.call_args.args[1], (300, 240))

    def test_missing_calibration_does_not_capture_or_change_monitoring(self):
        self.engine._enabled.set()
        with patch.object(self.engine, "_diagnostic_capture_context") as capture:
            self.assertIsNone(self.engine.save_debug_capture(AppConfig()))
        capture.assert_not_called()
        self.assertTrue(self.engine.is_monitoring())
        self.assertEqual(self.events[-1].snapshot_state, "failed")

    def test_capture_failure_does_not_report_success_or_critical_stop(self):
        with (
            patch.object(self.engine, "_diagnostic_capture_context", side_effect=RuntimeError("窗口最小化")),
            patch("fishing_assistant.engine.record_error"),
        ):
            self.assertIsNone(self.engine.save_debug_capture())
        self.assertEqual(self.events[-1].kind, EventKind.DIAGNOSTIC)
        self.assertEqual(self.events[-1].snapshot_state, "failed")
        self.assertIsNone(self.events[-1].diagnostic_path)

    def test_image_write_failure_reports_partial_success(self):
        with (
            TemporaryDirectory() as tmp,
            patch("fishing_assistant.engine.VISION_DIAGNOSTICS_DIR", Path(tmp)),
            patch.object(self.engine, "_diagnostic_capture_context", return_value=self.context),
            patch("fishing_assistant.engine.vision_diagnostics.run_pipeline_check", return_value=None),
            patch("fishing_assistant.engine.vision_diagnostics.collect_environment", return_value={}),
            patch("pathlib.Path.write_bytes", side_effect=OSError("disk failure")),
            patch("fishing_assistant.engine.record_error"),
        ):
            self.assertIsNone(self.engine.save_debug_capture())
            self.assertEqual(self.events[-1].snapshot_state, "partial")
            self.assertTrue(self.events[-1].diagnostic_path.is_file())
            self.assertIsNone(self.events[-1].debug_image)

    def test_f9_runs_asynchronously_deduplicates_and_keeps_f8_responsive(self):
        entered, release = threading.Event(), threading.Event()

        def save(_config):
            entered.set()
            if not release.wait(2):
                raise RuntimeError("test timeout")

        with patch.object(self.engine, "save_debug_capture", side_effect=save) as saved:
            try:
                self.assertTrue(self.engine.request_debug_capture())
                self.assertTrue(entered.wait(1))
                self.assertFalse(self.engine.request_debug_capture())
                with patch.object(self.engine, "toggle_monitoring") as toggle:
                    self.engine._on_key_press(keyboard.Key.f8)
                    toggle.assert_called_once()
            finally:
                release.set()
                self.engine._debug_capture_thread.join(2)
            self.assertFalse(self.engine._debug_capture_thread.is_alive())
            self.assertTrue(self.engine.request_debug_capture())
            self.engine._debug_capture_thread.join(2)
            self.assertEqual(saved.call_count, 2)

    def test_worker_failure_releases_lock_and_emits_finished_state(self):
        with (
            patch.object(self.engine, "save_debug_capture", side_effect=RuntimeError("worker failure")),
            patch("fishing_assistant.engine.record_error"),
        ):
            self.assertTrue(self.engine.request_debug_capture())
            self.engine._debug_capture_thread.join(2)
        self.assertEqual(self.events[-1].snapshot_state, "failed")
        self.assertFalse(self.engine._debug_capture_lock.locked())


class F9UiTests(unittest.TestCase):
    def test_diagnostic_progress_does_not_change_fishing_or_play_voice(self):
        owner = MagicMock()
        for state in ("saving", "saved", "failed", "partial"):
            MainWindow._consume_engine_event(owner, EngineEvent(
                EventKind.DIAGNOSTIC, "诊断保存", snapshot_state=state,
            ))
            owner.snapshot_button.setEnabled.assert_called_with(state != "saving")
        owner._set_runtime_state.assert_not_called()
        owner.start_button.setText.assert_not_called()
        owner.voice_player.play.assert_not_called()

    def test_view_missing_screenshot_has_clear_hint(self):
        owner = MagicMock()
        owner._last_snapshot_path = None
        with patch("fishing_assistant.ui.QDesktopServices.openUrl") as opened:
            MainWindow._view_snapshot(owner)
        opened.assert_not_called()
        owner.view_snapshot_button.setEnabled.assert_called_with(False)
        self.assertIn("重新按 F9", owner.snapshot_status.setText.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
