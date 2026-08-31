"""检测 v2 时间基准确认器：以持续时长取代连续帧计数。

连续 N 帧的去抖动与轮询节奏绑死（弱机 200ms/帧时 2 帧=400ms，快机
75ms/帧时=150ms），时间基准让确认行为与硬件解耦。
"""

import unittest

from fishing_assistant.vision.confirm import TemporalConfirmer


class TemporalConfirmerTests(unittest.TestCase):
    def _confirmer(self) -> TemporalConfirmer:
        return TemporalConfirmer(hold_seconds=0.15, clear_seconds=0.20)

    def test_new_state_needs_hold_duration(self) -> None:
        confirmer = self._confirmer()
        self.assertIsNone(confirmer.update("waiting_bite", 0.00))
        self.assertIsNone(confirmer.update("waiting_bite", 0.10))
        self.assertEqual(confirmer.update("waiting_bite", 0.15), "waiting_bite")

    def test_single_frame_glitch_is_ignored(self) -> None:
        confirmer = self._confirmer()
        confirmer.update("waiting_bite", 0.00)
        confirmer.update("waiting_bite", 0.15)
        # 一帧 fish_hooked 毛刺后回到 waiting：确认状态不变。
        self.assertEqual(confirmer.update("fish_hooked", 0.20), "waiting_bite")
        self.assertEqual(confirmer.update("waiting_bite", 0.28), "waiting_bite")
        self.assertEqual(confirmer.update("waiting_bite", 0.50), "waiting_bite")

    def test_unknown_gap_keeps_confirmed_state(self) -> None:
        confirmer = self._confirmer()
        confirmer.update("ready_to_cast", 0.00)
        confirmer.update("ready_to_cast", 0.15)
        # 模糊帧（unknown）短于 clear_seconds：保持已确认状态。
        self.assertEqual(confirmer.update("unknown", 0.25), "ready_to_cast")
        self.assertEqual(confirmer.update("unknown", 0.34), "ready_to_cast")

    def test_sustained_unknown_clears_state(self) -> None:
        confirmer = self._confirmer()
        confirmer.update("ready_to_cast", 0.00)
        confirmer.update("ready_to_cast", 0.15)
        confirmer.update("unknown", 0.25)
        self.assertIsNone(confirmer.update("unknown", 0.46))

    def test_state_switch_needs_hold(self) -> None:
        confirmer = self._confirmer()
        confirmer.update("waiting_bite", 0.00)
        confirmer.update("waiting_bite", 0.15)
        confirmer.update("fish_hooked", 0.30)
        # 新状态持续未满 hold：仍回报旧状态。
        self.assertEqual(confirmer.update("fish_hooked", 0.40), "waiting_bite")
        self.assertEqual(confirmer.update("fish_hooked", 0.45), "fish_hooked")

    def test_slow_polling_confirms_on_elapsed_time(self) -> None:
        # 弱机 200ms/帧：第二帧观测已超过 hold 时长，直接确认。
        confirmer = self._confirmer()
        self.assertIsNone(confirmer.update("waiting_bite", 0.00))
        self.assertEqual(confirmer.update("waiting_bite", 0.20), "waiting_bite")

    def test_reset_clears_everything(self) -> None:
        confirmer = self._confirmer()
        confirmer.update("waiting_bite", 0.00)
        confirmer.update("waiting_bite", 0.15)
        confirmer.reset()
        self.assertIsNone(confirmer.update("waiting_bite", 0.20))


if __name__ == "__main__":
    unittest.main()
