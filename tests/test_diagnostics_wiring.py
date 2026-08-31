"""诊断机制的引擎接线：启动体检警示、连续未识别自动取证、F9 诊断包。

契约：诊断永不打断识别主路径；自动取证有阈值+冷却+次数上限，
防止磁盘被刷爆；环境收集不到时宁缺勿假（不发假警示）。
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np

from fishing_assistant.config import AppConfig
from fishing_assistant.engine import EventKind, FishingEngine, IconState


def _frame() -> np.ndarray:
    return np.full((180, 160, 3), 70, dtype=np.uint8)


class EnvironmentWarningTest(unittest.TestCase):
    def test_virtualized_dpi_emits_warning(self):
        events = []
        engine = FishingEngine(events.append)
        env = {
            "available": True,
            "dpi": {"virtualized": True, "scale": 1.25},
            "window_mode": "fullscreen",
        }
        with patch(
            "fishing_assistant.vision.diagnostics.collect_environment",
            return_value=env,
        ):
            engine._emit_environment_warnings()
        warnings = [e for e in events if e.kind == EventKind.WARNING]
        self.assertTrue(any("缩放" in e.message for e in warnings))

    def test_clean_environment_emits_nothing(self):
        events = []
        engine = FishingEngine(events.append)
        env = {
            "available": True,
            "dpi": {"virtualized": False, "scale": 1.0},
            "window_mode": "fullscreen",
        }
        with patch(
            "fishing_assistant.vision.diagnostics.collect_environment",
            return_value=env,
        ):
            engine._emit_environment_warnings()
        self.assertFalse([e for e in events if e.kind == EventKind.WARNING])

    def test_collector_crash_never_propagates(self):
        engine = FishingEngine(lambda e: None)
        with patch(
            "fishing_assistant.vision.diagnostics.collect_environment",
            side_effect=RuntimeError("boom"),
        ):
            engine._emit_environment_warnings()  # 不抛即通过


class UnrecognizedStreakTest(unittest.TestCase):
    """连续未识别（IconState.NORMAL）超阈值时自动落一份诊断快照。"""

    def setUp(self):
        self.engine = FishingEngine(lambda e: None)
        self.config = AppConfig(button_center=(80, 90))
        self.calls = []
        self.engine.export_diagnostic_snapshot = (
            lambda reason, frame=None, config=None: self.calls.append(reason)
        )

    def _feed(self, state, at):
        self.engine._track_unrecognized(state, at, self.config)

    def test_short_streak_does_not_trigger(self):
        """收鱼动画等暂态也会短暂 NORMAL——阈值内绝不能触发。"""
        for second in range(0, 15, 3):
            self._feed(IconState.NORMAL, 100.0 + second)
        self.assertEqual(self.calls, [])

    def test_long_streak_triggers_once(self):
        for second in range(0, 30, 3):
            self._feed(IconState.NORMAL, 100.0 + second)
        self.assertEqual(len(self.calls), 1)

    def test_recognized_state_resets_streak(self):
        self._feed(IconState.NORMAL, 100.0)
        self._feed(IconState.WAITING_BITE, 115.0)
        self._feed(IconState.NORMAL, 116.0)
        self._feed(IconState.NORMAL, 130.0)
        self.assertEqual(self.calls, [])

    def test_cooldown_blocks_rapid_refire(self):
        for second in range(0, 90, 3):
            self._feed(IconState.NORMAL, 100.0 + second)
        # 90 秒全程未识别：首发一次 + 冷却后最多一次。
        self.assertLessEqual(len(self.calls), 2)

    def test_session_capped_at_max_snapshots(self):
        for second in range(0, 3600, 3):
            self._feed(IconState.NORMAL, 100.0 + second)
        self.assertLessEqual(len(self.calls), 3)


class ExportSnapshotTest(unittest.TestCase):
    def test_export_writes_zip_and_emits_path(self):
        events = []
        engine = FishingEngine(events.append)
        config = AppConfig(button_center=(80, 90))
        with TemporaryDirectory() as tmp:
            path = engine.export_diagnostic_snapshot(
                "测试取证", frame=_frame(), config=config, out_dir=Path(tmp)
            )
            self.assertIsNotNone(path)
            self.assertTrue(path.exists())
            self.assertEqual(path.suffix, ".zip")
        self.assertTrue(
            any("诊断" in e.message for e in events if e.kind == EventKind.SUCCESS)
        )

    def test_export_failure_degrades_to_warning(self):
        """快照失败只能变成一条警示，绝不能中断监测循环。"""
        events = []
        engine = FishingEngine(events.append)
        config = AppConfig(button_center=(80, 90))
        with TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "blocker"
            blocker.write_text("occupied")
            # 以文件为父路径：mkdir 在任何平台都必然失败。
            result = engine.export_diagnostic_snapshot(
                "测试", frame=_frame(), config=config, out_dir=blocker / "diag"
            )
        self.assertIsNone(result)
        self.assertTrue([e for e in events if e.kind == EventKind.WARNING])

class CorrectedDiagnosticIntegrationTest(unittest.TestCase):
    def test_window_context_uses_full_frame_and_window_relative_center(self):
        engine = FishingEngine(lambda event: None)
        config = AppConfig(
            capture_mode="window",
            window_backend="ok",
            target_window_handle=101,
            target_window_title="瑪奇 Mobile",
            button_center=(1700, 900),
            target_button_offset=(1500, 800),
        )
        target = __import__(
            "fishing_assistant.window_target", fromlist=["WindowInfo"]
        ).WindowInfo(101, "瑪奇 Mobile", 100, 50, 1918, 1030)
        full_frame = np.zeros((1030, 1918, 4), dtype=np.uint8)
        with patch.object(engine, "_resolve_target_window", return_value=target):
            with patch.object(
                engine, "_capture_stamina_frame", return_value=full_frame
            ) as capture:
                frame, center, info = engine._diagnostic_capture_context(
                    config, capture_frame=True
                )
        capture.assert_called_once_with(None, config)
        self.assertEqual(frame.shape, (1030, 1918, 3))
        self.assertEqual(center, (1500, 800))
        self.assertEqual(info["expected_size"], [1918, 1030])
        self.assertEqual(info["button_center"], [1500, 800])

    def test_new_monitoring_session_resets_snapshot_limits(self):
        engine = FishingEngine(lambda event: None)
        engine._config = AppConfig(capture_mode="screen", button_center=(100, 100))
        engine._unrecognized_since = 10.0
        engine._last_diag_snapshot_at = 20.0
        engine._diag_snapshot_count = 3
        with patch.object(engine, "_prepare_stamina_view"):
            with patch.object(engine, "_emit_environment_warnings"):
                self.assertTrue(engine.set_monitoring(True))
        self.assertIsNone(engine._unrecognized_since)
        self.assertIsNone(engine._last_diag_snapshot_at)
        self.assertEqual(engine._diag_snapshot_count, 0)
        engine.set_monitoring(False)

class CoordinateAndSupportBundleTest(unittest.TestCase):
    def test_secondary_monitor_center_is_converted_to_frame_coordinates(self):
        engine = FishingEngine(lambda event: None)
        config = AppConfig(
            capture_mode="screen",
            monitor_index=1,
            button_center=(-100, 900),
        )

        class FakeScreen:
            monitors = [
                {"left": -1920, "top": 0, "width": 3840, "height": 1080},
                {"left": -1920, "top": 0, "width": 1920, "height": 1080},
            ]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def grab(self, monitor):
                return np.zeros(
                    (monitor["height"], monitor["width"], 4), dtype=np.uint8
                )

        with patch("fishing_assistant.engine.mss.MSS", return_value=FakeScreen()):
            frame, center, info = engine._diagnostic_capture_context(
                config, capture_frame=True
            )
        self.assertEqual(frame.shape, (1080, 1920, 3))
        self.assertEqual(center, (1820, 900))
        self.assertEqual(info["monitor_origin"], [-1920, 0])

    def test_support_bundle_includes_recent_vision_diagnostic(self):
        import zipfile
        from fishing_assistant import diagnostics

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            support = root / "support"
            vision = root / "vision"
            vision.mkdir()
            snapshot = vision / "diagnostic-test.zip"
            snapshot.write_bytes(b"local diagnostic")
            with patch.object(diagnostics, "SUPPORT_DIR", support):
                with patch.object(diagnostics, "VISION_DIAGNOSTICS_DIR", vision):
                    with patch.object(diagnostics, "LOG_DIR", root / "logs"):
                        with patch.object(
                            diagnostics, "PROFILE_PATH", root / "profile.json"
                        ):
                            bundle = diagnostics.create_support_bundle()
            with zipfile.ZipFile(bundle) as archive:
                names = set(archive.namelist())
        self.assertIn(
            "vision-diagnostics/diagnostic-test.zip",
            names,
        )


if __name__ == "__main__":
    unittest.main()
