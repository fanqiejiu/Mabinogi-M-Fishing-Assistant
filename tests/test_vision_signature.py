"""检测 v2 比例签名分类器：颜色占比 + 结构特征的状态判别。

契约：分类器判"画面呈现哪个状态外观"；转态动画残留判成该状态是正确
行为，滤除短暂外观由时间基准确认层负责。黄金集回归依赖本地帧库
（FISHING_E2E_FRAMES_DIR），未设置时自动跳过。
"""

import os
import re
import unittest
from pathlib import Path

import cv2
import numpy as np

from fishing_assistant.vision.calibration import load_button_templates
from fishing_assistant.vision.signature import (
    SIGNATURE_STATES,
    classify_signature,
    extract_signature,
    locate_button_in_roi,
)

FRAMES_ENV = "FISHING_E2E_FRAMES_DIR"

# 模板图内按钮圆几何（与 calibration 的离线量测一致）。
_TEMPLATE_CIRCLES = {
    "waiting_bite": (67, 81, 142.2),
    "fish_hooked": (77, 92, 141.3),
    "ready_to_cast": (75, 80, 142.2),
    "idle_recovery": (103, 110, 119.9),
}


def _frames_dir() -> Path | None:
    value = os.environ.get(FRAMES_ENV, "")
    path = Path(value)
    if value and path.is_dir():
        return path
    return None


class SignatureTemplateTests(unittest.TestCase):
    """状态图标模板自身必须被分类到对应状态（不依赖帧库）。"""

    def test_templates_classify_to_their_states(self) -> None:
        templates = load_button_templates()
        for name, (cx, cy, diameter) in _TEMPLATE_CIRCLES.items():
            template = templates[name]
            features = extract_signature(template, cx, cy, diameter)
            state, confidence = classify_signature(features)
            with self.subTest(template=name):
                self.assertEqual(state, name)
                self.assertGreater(confidence, 0.0)

    def test_blank_image_is_unknown(self) -> None:
        blank = np.full((160, 180, 3), 70, dtype=np.uint8)
        features = extract_signature(blank, 80, 90, 150)
        state, confidence = classify_signature(features)
        self.assertEqual(state, "unknown")
        self.assertEqual(confidence, 0.0)

    def test_signature_states_cover_four_icons(self) -> None:
        self.assertEqual(
            set(SIGNATURE_STATES),
            {"waiting_bite", "fish_hooked", "ready_to_cast", "idle_recovery"},
        )


@unittest.skipUnless(
    _frames_dir() is not None,
    f"set {FRAMES_ENV} to run frame-library regression tests",
)
class SignatureGoldenSetTests(unittest.TestCase):
    """帧库黄金集：状态帧全对；已知非按钮画面必须拒判。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = _frames_dir()

    def _classify_file(self, relative: str) -> tuple[str, float]:
        path = self.frames / relative
        roi = cv2.imread(str(path))
        self.assertIsNotNone(roi, f"帧文件缺失：{path}")
        circle = locate_button_in_roi(roi)
        if circle is None:
            return "no-circle", 0.0
        cx, cy, radius = circle
        features = extract_signature(roi, cx, cy, 2 * radius)
        return classify_signature(features)

    def test_all_labeled_state_frames_classify_correctly(self) -> None:
        pattern = re.compile(r"tr_\d+_(.+)\.png")
        total = 0
        for run in ("dryrun1", "dryrun2"):
            for path in sorted((self.frames / run).glob("tr_*.png")):
                label = pattern.match(path.name).group(1)
                if label not in SIGNATURE_STATES:
                    continue
                total += 1
                state, _ = self._classify_file(f"{run}/{path.name}")
                with self.subTest(frame=f"{run}/{path.name}"):
                    self.assertEqual(state, label)
        self.assertGreaterEqual(total, 40, "标签状态帧数量不足")

    def test_dark_frame_still_classifies(self) -> None:
        # 夜间/阴影画面：亮度归一化后白方块必须仍可识别。
        state, _ = self._classify_file("dryrun1/tr_06665_waiting_bite.png")
        self.assertEqual(state, "waiting_bite")

    def test_loading_overlay_is_rejected(self) -> None:
        # dryrun2 首帧：读条浮水印画面，不得误判为任何状态。
        state, _ = self._classify_file("dryrun2/tr_00000_normal.png")
        self.assertIn(state, ("unknown", "no-circle"))

    def test_reward_overlay_is_rejected(self) -> None:
        # 收鱼奖励动画（半透明鱼浮水印+金光）曾以 0.26-0.49 低信心穿过
        # idle 判别式（实机 shadow 实证）；真指南针中心必有黑点，浮水印
        # 没有——中心暗点特征必须把这类画面挡在 idle 之外。
        overlay_dir = self.frames / "shadow1" / "v2_shadow"
        frames = sorted(overlay_dir.glob("diff_normal-vs-idle_recovery_*.png"))
        if not frames:
            self.skipTest("shadow1 奖励动画分歧帧不在帧库中")
        for path in frames:
            state, _ = self._classify_file(f"shadow1/v2_shadow/{path.name}")
            with self.subTest(frame=path.name):
                self.assertIn(state, ("unknown", "no-circle"))

    def test_transition_frame_anchor_cases(self) -> None:
        # 人工核对过画面真值的过渡帧锚点（引擎标签为 normal 的转态时刻）：
        # 画面呈现清晰状态外观的判成该状态；杂合叠加画面（指南针盖住
        # 鱼竿等）的低信心命中必须被分层阈值滤成 unknown。
        anchors = {
            "dryrun2/tr_01940_normal.png": {"waiting_bite"},  # 清晰白方块
            # 鱼竿+水面为主体但被绿环叠加：判 ready 或降级仲裁都合理。
            "dryrun2/tr_01695_normal.png": {"ready_to_cast", "unknown", "no-circle"},
            "dryrun2/tr_01680_normal.png": {"unknown", "no-circle"},  # 杂合叠加
            "dryrun1/tr_06573_normal.png": {"waiting_bite"},  # 引擎跟丢的白方块
            "dryrun1/tr_06688_normal.png": {"waiting_bite"},  # 暗版白方块
        }
        for relative, allowed in anchors.items():
            state, _ = self._classify_file(relative)
            with self.subTest(frame=relative):
                self.assertIn(state, allowed)


if __name__ == "__main__":
    unittest.main()
