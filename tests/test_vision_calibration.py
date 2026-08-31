"""检测 v2 自动校准：按钮圆几何定位 + 内容验证。

帧库回归测试依赖本地 E2E 帧库（不随仓库分发）：
设置环境变量 FISHING_E2E_FRAMES_DIR 指向帧库目录后运行；未设置时自动跳过。
"""

import os
import unittest
from pathlib import Path

import cv2
import numpy as np

from fishing_assistant.vision.calibration import (
    REFERENCE_DIAMETER,
    ButtonCalibration,
    calibrate_button,
    load_button_templates,
)

FRAMES_ENV = "FISHING_E2E_FRAMES_DIR"

# E2E 实测基准：1920x1080 无边框窗口下钓鱼按钮中心。
LIVE_BUTTON_CENTER = (1804, 962)


def _frames_dir() -> Path | None:
    value = os.environ.get(FRAMES_ENV, "")
    path = Path(value)
    if value and path.is_dir():
        return path
    return None


class SyntheticCalibrationTests(unittest.TestCase):
    """不依赖帧库的合成画面测试：几何定位与内容验证的基本契约。"""

    def setUp(self) -> None:
        self.templates = load_button_templates()

    def _canvas_with_template(
        self, template: np.ndarray, top_left: tuple[int, int]
    ) -> np.ndarray:
        canvas = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        h, w = template.shape[:2]
        x, y = top_left
        canvas[y : y + h, x : x + w] = template
        return canvas

    def test_loads_all_button_templates(self) -> None:
        self.assertGreaterEqual(len(self.templates), 3)
        for name, image in self.templates.items():
            self.assertEqual(image.ndim, 3, name)

    def test_finds_pasted_button_template(self) -> None:
        template = self.templates["ready_to_cast"]
        canvas = self._canvas_with_template(template, (1720, 880))
        result = calibrate_button(canvas, self.templates)
        self.assertIsInstance(result, ButtonCalibration)
        # 模板圆心位于模板内 (75, 80) 附近；允许几何检测的像素级抖动。
        expected = (1720 + 75, 880 + 80)
        self.assertLess(abs(result.center[0] - expected[0]), 8)
        self.assertLess(abs(result.center[1] - expected[1]), 8)
        self.assertGreater(result.confidence, 0.7)

    def test_rejects_blank_canvas(self) -> None:
        canvas = np.full((1080, 1920, 3), 70, dtype=np.uint8)
        self.assertIsNone(calibrate_button(canvas, self.templates))

    def test_scale_fields_are_consistent(self) -> None:
        template = self.templates["ready_to_cast"]
        canvas = self._canvas_with_template(template, (1720, 880))
        result = calibrate_button(canvas, self.templates)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(
            result.scale, result.diameter / REFERENCE_DIAMETER, places=6
        )


@unittest.skipUnless(
    _frames_dir() is not None,
    f"set {FRAMES_ENV} to run frame-library regression tests",
)
class LiveFrameCalibrationTests(unittest.TestCase):
    """真实战斗帧回归：命中率、尺度稳定性与真阴性。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = _frames_dir()
        cls.templates = load_button_templates()

    def _calibrate_file(self, relative: str) -> ButtonCalibration | None:
        path = self.frames / relative
        frame = cv2.imread(str(path))
        self.assertIsNotNone(frame, f"帧文件缺失：{path}")
        return calibrate_button(frame, self.templates)

    def test_locates_button_across_live_snapshots(self) -> None:
        snapshots = sorted((self.frames / "c3").glob("snap_*success*.png"))[:12]
        self.assertGreaterEqual(len(snapshots), 8, "c3 快照数量不足")
        for path in snapshots:
            frame = cv2.imread(str(path))
            result = calibrate_button(frame, self.templates)
            with self.subTest(frame=path.name):
                self.assertIsNotNone(result)
                error = (
                    (result.center[0] - LIVE_BUTTON_CENTER[0]) ** 2
                    + (result.center[1] - LIVE_BUTTON_CENTER[1]) ** 2
                ) ** 0.5
                self.assertLess(error, 15.0)
                self.assertGreater(result.scale, 0.90)
                self.assertLess(result.scale, 1.10)

    def test_downscaled_frame_yields_proportional_scale(self) -> None:
        path = self.frames / "c3" / "snap_003_0017s_success.png"
        frame = cv2.imread(str(path))
        small = cv2.resize(frame, (1366, 768), interpolation=cv2.INTER_AREA)
        result = calibrate_button(small, self.templates)
        self.assertIsNotNone(result, "1366x768 降采样帧必须仍可校准")
        expected_scale = 768 / 1080
        self.assertLess(abs(result.scale - expected_scale), 0.06)
        # 相对坐标应与原帧一致（按钮随画面等比缩放）。
        self.assertLess(
            abs(result.center[0] / 1366 - LIVE_BUTTON_CENTER[0] / 1920), 0.02
        )
        self.assertLess(
            abs(result.center[1] / 768 - LIVE_BUTTON_CENTER[1] / 1080), 0.02
        )

    def test_calibrates_on_idle_compass_state(self) -> None:
        # 启动脚本时按钮最常处于指南针（idle）状态；三张 start 帧覆盖
        # 霍夫圆命中内盘（c1/c3）与外环（c2）两种几何解释。
        for relative in (
            "c1/snap_000_0000s_start.png",
            "c2/snap_000_0000s_start.png",
            "c3/snap_000_0000s_start.png",
        ):
            with self.subTest(frame=relative):
                result = self._calibrate_file(relative)
                self.assertIsNotNone(result)
                error = (
                    (result.center[0] - LIVE_BUTTON_CENTER[0]) ** 2
                    + (result.center[1] - LIVE_BUTTON_CENTER[1]) ** 2
                ) ** 0.5
                self.assertLess(error, 15.0)
                self.assertGreater(result.scale, 0.90)
                self.assertLess(result.scale, 1.10)

    def test_rejects_frame_without_button(self) -> None:
        # C2 结束帧：钓鱼界面已收起，画面上没有钓鱼按钮。
        self.assertIsNone(self._calibrate_file("c2/snap_030_0301s_end.png"))

    def test_rejects_inventory_icon_frame(self) -> None:
        # C3 警告帧：右下角是背包图标（同为圆形黄底），不得误认成钓鱼按钮。
        self.assertIsNone(self._calibrate_file("c3/snap_007_0087s_warning.png"))


if __name__ == "__main__":
    unittest.main()
