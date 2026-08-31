"""诊断体检模块：环境事实解读、识别管线分层试跑、诊断快照落盘。

契约：诊断层永不抛异常、永不影响识别主路径；每层输出独立可读
（"未命中"是数据不是错误——校准在非钓鱼画面正确拒绝属正常行为）。
环境收集在非 Windows 平台降级为 available=False，其余功能照常。
"""

import json
import os
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from fishing_assistant.vision.diagnostics import (
    PipelineCheck,
    collect_environment,
    describe_capture_scale,
    describe_dpi_virtualization,
    run_pipeline_check,
    summarize_environment,
    write_snapshot,
)

FRAMES_ENV = "FISHING_E2E_FRAMES_DIR"


def _sample_frame() -> np.ndarray | None:
    value = os.environ.get(FRAMES_ENV, "")
    if not value:
        return None
    import cv2

    for pattern in ("snap_*.png", "*/snap_*.png"):
        for path in sorted(Path(value).glob(pattern))[:1]:
            return cv2.imread(str(path))
    return None


class DescribeDpiVirtualizationTest(unittest.TestCase):
    def test_125_percent_scaling_detected(self):
        """unaware 视野比物理小 1.25 倍 = 进程若未声明 DPI 感知会拿到放大模糊帧。"""
        result = describe_dpi_virtualization((1536, 864), (1920, 1080))
        self.assertTrue(result["virtualized"])
        self.assertAlmostEqual(result["scale"], 1.25, places=2)

    def test_no_scaling_when_sizes_match(self):
        result = describe_dpi_virtualization((1920, 1080), (1920, 1080))
        self.assertFalse(result["virtualized"])
        self.assertAlmostEqual(result["scale"], 1.0, places=2)

    def test_degenerate_sizes_do_not_raise(self):
        """任何输入都不能让诊断层自己炸掉。"""
        for bad in ((0, 0), (None, None)):
            result = describe_dpi_virtualization(bad, (1920, 1080))
            self.assertFalse(result["virtualized"])



class DescribeCaptureScaleTest(unittest.TestCase):
    def test_matching_capture_size_is_clean(self):
        result = describe_capture_scale((1920, 1080), (1080, 1920, 3))
        self.assertFalse(result["mismatch"])

    def test_scaled_capture_is_reported(self):
        result = describe_capture_scale((1920, 1080), (864, 1536, 3))
        self.assertTrue(result["mismatch"])
        self.assertEqual(result["frame_size"], [1536, 864])
class RunPipelineCheckTest(unittest.TestCase):
    def test_black_frame_reports_not_found_without_raising(self):
        """全黑帧上三层都应「执行成功但未命中」——未命中是数据不是错误。"""
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        check = run_pipeline_check(frame, button_center=(1804, 962))
        self.assertIsInstance(check, PipelineCheck)
        for name in ("calibration", "signature", "stamina"):
            layer = check.layer(name)
            self.assertIsNotNone(layer, name)
            self.assertTrue(layer.ok, name)
            self.assertFalse(layer.found, name)

    def test_missing_button_center_still_runs_frame_layers(self):
        """没做过 F7 校准的用户也要能出诊断：签名层跳过并说明原因。"""
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        check = run_pipeline_check(frame, button_center=None)
        signature = check.layer("signature")
        self.assertTrue(signature.ok)
        self.assertFalse(signature.found)
        self.assertIn("button_center", signature.detail.get("skipped", ""))
        self.assertTrue(check.layer("calibration").ok)

    def test_invalid_frame_degrades_to_all_layers_failed(self):
        check = run_pipeline_check(None, button_center=(100, 100))
        for layer in check.layers:
            self.assertFalse(layer.found)

    def test_real_frame_signature_layer_hits(self):
        """真实战帧上签名层应命中一个状态（黄金帧回归，帧库缺席跳过）。"""
        frame = _sample_frame()
        if frame is None:
            self.skipTest("FISHING_E2E_FRAMES_DIR not available")
        check = run_pipeline_check(frame, button_center=(1804, 962))
        signature = check.layer("signature")
        self.assertTrue(signature.ok)


class CollectEnvironmentTest(unittest.TestCase):
    def test_returns_dict_and_never_raises_off_windows(self):
        env = collect_environment()
        self.assertIsInstance(env, dict)
        self.assertIn("available", env)


class SummarizeEnvironmentTest(unittest.TestCase):
    def test_dpi_virtualization_produces_warning(self):
        """DPI 虚拟化是「检测不到」的头号环境根因，必须出现在警示里。"""
        env = {
            "available": True,
            "dpi": {"virtualized": True, "scale": 1.25},
            "window_mode": "fullscreen",
        }
        warnings = summarize_environment(env, frame_shape=(864, 1536, 3))
        self.assertTrue(any("DPI" in w or "缩放" in w for w in warnings))

    def test_windowed_mode_produces_warning(self):
        env = {
            "available": True,
            "dpi": {"virtualized": False, "scale": 1.0},
            "window_mode": "windowed",
        }
        warnings = summarize_environment(env, frame_shape=(1080, 1920, 3))
        self.assertTrue(any("窗口" in w for w in warnings))

    def test_clean_environment_produces_no_warnings(self):
        env = {
            "available": True,
            "dpi": {"virtualized": False, "scale": 1.0},
            "window_mode": "fullscreen",
        }
        self.assertEqual(summarize_environment(env, (1080, 1920, 3)), [])

    def test_unavailable_environment_yields_no_false_warnings(self):
        """收集不到环境事实时不能凭空报警（宁缺勿假）。"""
        self.assertEqual(summarize_environment({"available": False}, None), [])


class WriteSnapshotTest(unittest.TestCase):
    def test_snapshot_zip_contains_report_and_frame(self):
        frame = np.zeros((120, 160, 3), dtype=np.uint8)
        check = run_pipeline_check(frame, button_center=(80, 60))
        with TemporaryDirectory() as tmp:
            path = write_snapshot(
                Path(tmp),
                frame,
                reason="测试诊断",
                environment={"available": False},
                pipeline=check,
                config_summary={"display_mode": "borderless"},
            )
            self.assertTrue(path.exists())
            with zipfile.ZipFile(path) as bundle:
                names = set(bundle.namelist())
                self.assertIn("report.json", names)
                self.assertIn("frame.png", names)
                report = json.loads(bundle.read("report.json"))
        self.assertIn("environment", report)
        self.assertIn("pipeline", report)
        self.assertIn("config", report)
        self.assertIn("app_version", report)

    def test_snapshot_survives_missing_frame(self):
        """抓不到帧时快照仍要产出（报告本身就是证据）。"""
        with TemporaryDirectory() as tmp:
            path = write_snapshot(
                Path(tmp),
                None,
                reason="无画面诊断",
                environment={"available": False},
                pipeline=None,
                config_summary={},
            )
            self.assertTrue(path.exists())
            with zipfile.ZipFile(path) as bundle:
                self.assertIn("report.json", bundle.namelist())


if __name__ == "__main__":
    unittest.main()
