"""检测 v2 决策路径切换：签名层先判、unknown 降级模板仲裁、开关可回退。

v2_vision_enabled=True（默认）时识别顺序：指南针像素校正 → v2 签名
（~0.2ms，绝大多数帧在此定案）→ FeatureSet 模板仲裁（签名 unknown 时）。
False 时完全回到旧路径。
"""

import os
import unittest
from pathlib import Path

import cv2
import numpy as np

from fishing_assistant.config import AppConfig
from fishing_assistant.constants import OK_ICON_TEMPLATE_PATHS
from fishing_assistant.engine import FishingEngine, IconState

FRAMES_ENV = "FISHING_E2E_FRAMES_DIR"


def _frames_dir() -> Path | None:
    value = os.environ.get(FRAMES_ENV, "")
    path = Path(value)
    if value and path.is_dir():
        return path
    return None


def _template_roi(name: str) -> np.ndarray:
    """把状态模板贴到 ROI 尺寸画布上，构造识别输入帧。"""
    template = cv2.imread(str(OK_ICON_TEMPLATE_PATHS[name]))
    height, width = template.shape[:2]
    canvas = np.full((height + 12, width + 12, 3), 70, dtype=np.uint8)
    canvas[6 : 6 + height, 6 : 6 + width] = template
    return canvas


class V2SwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig(v2_vision_enabled=True)

    def test_config_default_enables_v2(self) -> None:
        self.assertTrue(AppConfig().v2_vision_enabled)

    def test_signature_path_classifies_state_frame(self) -> None:
        roi = _template_roi("ready_to_cast")
        state, signals = FishingEngine.classify_frame_state(roi, self.config)
        self.assertEqual(state, IconState.READY_TO_CAST)
        self.assertEqual(signals.recognition_source, "v2_signature")
        self.assertGreater(signals.recognition_confidence, 0.0)

    def test_unknown_signature_falls_back_to_template_scan(self) -> None:
        # 空白画布：签名 unknown → 降级 FeatureSet，来源必须是 ok_feature。
        blank = np.full((180, 160, 3), 70, dtype=np.uint8)
        state, signals = FishingEngine.classify_frame_state(blank, self.config)
        self.assertEqual(state, IconState.NORMAL)
        self.assertEqual(signals.recognition_source, "ok_feature")

    def test_horse_prompt_resolved_by_arbitration(self) -> None:
        # 骑马提示被签名层拒判（center_white 隔离），必须由模板仲裁层判出。
        roi = _template_roi("horse_mount_prompt")
        state, signals = FishingEngine.classify_frame_state(roi, self.config)
        self.assertEqual(state, IconState.HORSE_MOUNT_PROMPT)
        self.assertEqual(signals.recognition_source, "ok_feature")

    def test_disabled_switch_restores_legacy_path(self) -> None:
        config = AppConfig(v2_vision_enabled=False)
        roi = _template_roi("ready_to_cast")
        state, signals = FishingEngine.classify_frame_state(roi, config)
        self.assertEqual(state, IconState.READY_TO_CAST)
        self.assertEqual(signals.recognition_source, "ok_feature")


@unittest.skipUnless(
    _frames_dir() is not None,
    f"set {FRAMES_ENV} to run frame-library regression tests",
)
class V2StaminaSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = _frames_dir()

    def test_v2_sample_from_live_frame(self) -> None:
        # C3 实战帧：v2 读条定位结果必须转成引擎的 StaminaBarSample 结构。
        frame = cv2.imread(str(self.frames / "c3" / "snap_020_0270s_success.png"))
        engine = FishingEngine.__new__(FishingEngine)
        engine._stamina_last_center = None
        sample = engine._find_stamina_bar_v2_sample(frame)
        self.assertIsNotNone(sample)
        self.assertLess(abs(sample.fill_left - 876), 10)
        self.assertGreater(sample.fill_width, 20)
        self.assertGreaterEqual(sample.anchor_confidence, 0.70)

    def test_v2_sample_none_when_no_bar(self) -> None:
        frame = cv2.imread(str(self.frames / "c3" / "snap_015_0192s_success.png"))
        engine = FishingEngine.__new__(FishingEngine)
        engine._stamina_last_center = None
        self.assertIsNone(engine._find_stamina_bar_v2_sample(frame))


if __name__ == "__main__":
    unittest.main()
