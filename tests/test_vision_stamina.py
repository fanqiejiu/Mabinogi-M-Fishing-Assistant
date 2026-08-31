"""检测 v2 体力条定位：降采样粗扫 + 原图窗口精读 + 锚点弱确认。

黄金集为 C3 实战帧：6 张真条帧（战斗收杆时刻）、2 张画面左下有
UI 假绿条的帧、以及无条帧。依赖 FISHING_E2E_FRAMES_DIR。
"""

import os
import unittest
from pathlib import Path

import cv2

from fishing_assistant.vision.stamina import StaminaBarV2, find_stamina_bar_v2

FRAMES_ENV = "FISHING_E2E_FRAMES_DIR"

# C3 实战帧的真条几何（断点诊断探针量测：fill 左缘 x, y, 宽）。
# 注：这根条是角色头顶的拉线读条（图标=鱼竿抛线，条下方是角色名），
# 功能上即战斗状态显示器——鱼挣扎时条被消耗、鱼力竭时恢复。
_TRUE_BARS = {
    "snap_010_0122s_success.png": (862, 219, 141),
    "snap_020_0270s_success.png": (876, 216, 89),
    "snap_022_0287s_success.png": (851, 216, 84),
    "snap_024_0303s_success.png": (842, 217, 88),
    "snap_028_0352s_success.png": (874, 217, 86),
    "snap_038_0500s_success.png": (863, 215, 140),
}

# C1/C2 会话（另一镜头 zoom，条在 y≈405）的真条锚点样本（画面人工核对）。
_TRUE_BARS_OTHER_RUNS = {
    "c1/snap_003_0009s_success.png": (873, 407),
    "c1/snap_020_0144s_success.png": (872, 405),
    "c2/snap_003_0015s_success.png": (871, 402),
    "c2/snap_024_0223s_success.png": (875, 401),
}

# 左下角出现 UI 假绿条（锚点分数 0.45）的帧：不得误报。
_FAKE_BAR_FRAMES = (
    "snap_036_0467s_success.png",
    "snap_037_0483s_success.png",
)

# 无任何战斗条的普通收杆帧。
_NO_BAR_FRAMES = (
    "snap_003_0017s_success.png",
    "snap_015_0192s_success.png",
    "snap_033_0420s_success.png",
)


def _frames_dir() -> Path | None:
    value = os.environ.get(FRAMES_ENV, "")
    path = Path(value)
    if value and path.is_dir():
        return path
    return None


@unittest.skipUnless(
    _frames_dir() is not None,
    f"set {FRAMES_ENV} to run frame-library regression tests",
)
class StaminaBarV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frames = _frames_dir()

    def _find(self, name: str) -> StaminaBarV2 | None:
        frame = cv2.imread(str(self.frames / "c3" / name))
        self.assertIsNotNone(frame, f"帧文件缺失：{name}")
        return find_stamina_bar_v2(frame)

    def test_locates_all_true_bars(self) -> None:
        for name, (x, y, width) in _TRUE_BARS.items():
            with self.subTest(frame=name):
                bar = self._find(name)
                self.assertIsNotNone(bar)
                self.assertLess(abs(bar.fill_left - x), 10)
                self.assertLess(abs(bar.center[1] - y), 14)
                self.assertLess(abs(bar.fill_width - width), 9)
                self.assertGreaterEqual(bar.anchor_confidence, 0.55)

    def test_locates_bars_in_other_sessions(self) -> None:
        # 不同镜头 zoom 下（C1/C2 会话）读条位置不同，仍须定位成功。
        for relative, (x, y) in _TRUE_BARS_OTHER_RUNS.items():
            with self.subTest(frame=relative):
                frame = cv2.imread(str(self.frames / relative))
                bar = find_stamina_bar_v2(frame)
                self.assertIsNotNone(bar)
                self.assertLess(abs(bar.fill_left - x), 12)
                self.assertLess(abs(bar.center[1] - y), 14)
                self.assertGreaterEqual(bar.anchor_confidence, 0.70)

    def test_rejects_ui_green_strip(self) -> None:
        # 画面左下角的 UI 绿条（重裁模板后锚点分数升到 0.65-0.66）：
        # 必须被中部位置带硬条件排除——角色读条只会出现在画面中部。
        for name in _FAKE_BAR_FRAMES:
            with self.subTest(frame=name):
                self.assertIsNone(self._find(name))

    def test_no_bar_on_plain_frames(self) -> None:
        for name in _NO_BAR_FRAMES:
            with self.subTest(frame=name):
                self.assertIsNone(self._find(name))

    def test_prefers_candidate_near_last_center(self) -> None:
        # 战斗中条位置连续；提供上一次中心时应回传同一根条。
        name = "snap_020_0270s_success.png"
        frame = cv2.imread(str(self.frames / "c3" / name))
        bar = find_stamina_bar_v2(frame, last_center=(920, 224))
        self.assertIsNotNone(bar)
        self.assertLess(abs(bar.fill_left - 876), 10)


if __name__ == "__main__":
    unittest.main()
