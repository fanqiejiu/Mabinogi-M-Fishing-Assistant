"""语音包发现、事件映射和防重入播放测试。"""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from fishing_assistant.engine import EventKind
from fishing_assistant.voice_alerts import (
    CRITICAL_STOP_CUE,
    F7_CALIBRATION_CUE,
    F8_START_CUE,
    INVENTORY_CLEANED_CUE,
    RECOGNITION_FAILED_CUE,
    VoiceAlertPlayer,
    cue_for_engine_event,
    discover_voice_packs,
)


class VoicePackTests(unittest.TestCase):
    def test_numbered_files_are_grouped_as_equal_event_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "新海天"
            character.mkdir()
            for filename in (
                "F8开始识别1.wav",
                "F8开始识别2.wav",
                "最小化.wav",
                "最小化1.wav",
            ):
                (character / filename).touch()

            packs = discover_voice_packs(root)

            self.assertEqual(len(packs["新海天"]["F8开始识别"]), 2)
            self.assertEqual(len(packs["新海天"]["最小化"]), 2)

    def test_selected_variant_is_played_by_serial_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "新海天"
            character.mkdir()
            first = character / "F8开始识别1.wav"
            second = character / "F8开始识别2.wav"
            first.touch()
            second.touch()
            played: list[Path] = []
            player = VoiceAlertPlayer(
                root,
                play_file=played.append,
                choose=lambda variants: variants[-1],
            )
            try:
                player.configure(True, "新海天")
                selected = player.play(F8_START_CUE)
                self.assertTrue(player.wait_until_idle())
                self.assertEqual(selected, second)
                self.assertEqual(played, [second])
            finally:
                player.close()

    def test_repeated_f7_is_not_queued_or_played_at_the_same_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            character = root / "新海天"
            character.mkdir()
            audio = character / "F7定位.wav"
            audio.touch()
            started = threading.Event()
            release = threading.Event()
            played: list[Path] = []

            def blocking_play(path: Path) -> None:
                played.append(path)
                started.set()
                release.wait(1.0)

            player = VoiceAlertPlayer(root, play_file=blocking_play)
            try:
                player.configure(True, "新海天")
                self.assertEqual(player.play(F7_CALIBRATION_CUE), audio)
                self.assertTrue(started.wait(1.0))
                self.assertIsNone(player.play(F7_CALIBRATION_CUE))
                self.assertIsNone(player.play(F7_CALIBRATION_CUE))
                release.set()
                self.assertTrue(player.wait_until_idle())
                self.assertEqual(played, [audio])
            finally:
                release.set()
                player.close()


class VoiceEventMappingTests(unittest.TestCase):
    def test_engine_messages_map_to_named_voice_files(self) -> None:
        cases = (
            (EventKind.SUCCESS, "F7 已校准后台目标", False, F7_CALIBRATION_CUE),
            (EventKind.STATE, "OK 指定窗口模式已启动；测试", True, F8_START_CUE),
            (
                EventKind.WARNING,
                "无法读取活鱼体力条：测试",
                True,
                RECOGNITION_FAILED_CUE,
            ),
            (
                EventKind.ERROR,
                "连续移动恢复达到上限，监测已停止",
                False,
                CRITICAL_STOP_CUE,
            ),
            (
                EventKind.SUCCESS,
                "背包自动整理完成：已退出背包",
                True,
                INVENTORY_CLEANED_CUE,
            ),
        )
        for kind, message, monitoring, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(
                    cue_for_engine_event(kind, message, monitoring), expected
                )


if __name__ == "__main__":
    unittest.main()
