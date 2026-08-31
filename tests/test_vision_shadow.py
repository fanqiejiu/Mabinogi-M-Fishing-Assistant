"""检测 v2 影子记录器：并行判定、对照记录、分歧帧采集。

影子模式契约:v2 链只观察不决策,任何内部异常都不得影响主循环。
"""

import json
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

from fishing_assistant.vision.shadow import ShadowRecorder


def _blank_roi() -> np.ndarray:
    return np.full((180, 160, 3), 70, dtype=np.uint8)


class ShadowRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = tempfile.TemporaryDirectory()
        self.out = Path(self._dir.name)
        self.recorder = ShadowRecorder(self.out)

    def tearDown(self) -> None:
        self.recorder.close()
        self._dir.cleanup()

    def _read_log(self) -> list[dict]:
        log = self.out / "shadow.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    def test_records_comparison_row(self) -> None:
        self.recorder.record_icon(_blank_roi(), "normal", 0.0, now=1.0)
        self.recorder.close()
        rows = self._read_log()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["engine"], "normal")
        self.assertIn("v2", row)
        self.assertIn("v2_confirmed", row)
        self.assertIn("agree", row)

    def test_no_frame_dump_when_agreeing(self) -> None:
        self.recorder.record_icon(_blank_roi(), "normal", 0.0, now=1.0)
        self.recorder.close()
        self.assertEqual(list(self.out.glob("*.png")), [])

    def test_disagreement_dumps_frame_with_rate_limit(self) -> None:
        roi = _blank_roi()
        # v2 判 unknown->normal，引擎宣称 fish_hooked：分歧，应存帧。
        for index in range(10):
            self.recorder.record_icon(
                roi, "fish_hooked", 0.9, now=1.0 + index * 0.1
            )
        self.recorder.close()
        dumps = list(self.out.glob("diff_*.png"))
        self.assertGreaterEqual(len(dumps), 1)
        self.assertLessEqual(len(dumps), ShadowRecorder.MAX_DUMPS_PER_KIND)

    def test_hooked_transition_captures_full_frame(self) -> None:
        full = np.full((1080, 1920, 3), 60, dtype=np.uint8)
        self.recorder.record_hook_transition(full, now=2.0)
        self.recorder.close()
        self.assertEqual(len(list(self.out.glob("hook_*.png"))), 1)

    def test_internal_errors_never_raise(self) -> None:
        # 坏帧（None / 错维度）不得让影子路径抛异常。
        self.recorder.record_icon(None, "normal", 0.0, now=1.0)
        self.recorder.record_icon(
            np.zeros((4,), dtype=np.uint8), "normal", 0.0, now=1.1
        )
        self.recorder.close()

    def test_close_is_idempotent(self) -> None:
        self.recorder.record_icon(_blank_roi(), "normal", 0.0, now=1.0)
        self.recorder.close()
        self.recorder.close()


if __name__ == "__main__":
    unittest.main()
