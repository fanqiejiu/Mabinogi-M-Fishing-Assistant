"""按 voice/人物名/事件名N.wav 组织并串行播放语音提醒。"""

from __future__ import annotations

import random
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

try:
    import winsound
except ImportError:  # pragma: no cover - 非 Windows 仅用于源码检查
    winsound = None  # type: ignore[assignment]

from .constants import VOICE_DIR


_NUMBERED_VARIANT = re.compile(r"\d+$")
_SUPPORTED_EXTENSIONS = {".wav"}

F7_CALIBRATION_CUE = "F7定位"
F8_START_CUE = "F8开始识别"
F8_STOP_CUE = "F8结束识别"
RECOGNITION_FAILED_CUE = "识别失败"
CRITICAL_STOP_CUE = "关键性停止"
INVENTORY_CLEANED_CUE = "清理背包完成"
WINDOW_MINIMIZED_CUE = "最小化"
WINDOW_RESTORED_CUE = "最大化"


def normalize_cue_name(filename: str | Path) -> str:
    """把“事件1.wav / 事件2.wav”归为同一个等概率事件。"""
    stem = Path(filename).stem.strip()
    return _NUMBERED_VARIANT.sub("", stem)


def discover_voice_packs(
    root: Path = VOICE_DIR,
) -> dict[str, dict[str, tuple[Path, ...]]]:
    """读取人物音色目录，并按去掉末尾编号后的文件名归组。"""
    packs: dict[str, dict[str, tuple[Path, ...]]] = {}
    if not root.is_dir():
        return packs
    for character_dir in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if not character_dir.is_dir() or character_dir.name.startswith("."):
            continue
        grouped: dict[str, list[Path]] = {}
        for audio_path in sorted(
            character_dir.iterdir(), key=lambda item: item.name.casefold()
        ):
            if (
                not audio_path.is_file()
                or audio_path.suffix.casefold() not in _SUPPORTED_EXTENSIONS
            ):
                continue
            cue = normalize_cue_name(audio_path)
            if cue:
                grouped.setdefault(cue, []).append(audio_path)
        if grouped:
            packs[character_dir.name] = {
                cue: tuple(paths) for cue, paths in grouped.items()
            }
    return packs


def cue_for_engine_event(kind: object, message: str, monitoring: bool) -> str | None:
    """按引擎事件和文件名约定选择提示；未匹配时保持安静。"""
    kind_value = getattr(kind, "value", kind)
    kind_text = str(kind_value).casefold()
    if kind_text == "success" and message.startswith("F7 已校准"):
        return F7_CALIBRATION_CUE
    if kind_text == "success" and (
        message.startswith("背包自动整理完成")
        or message.startswith("背包清理调试完成")
    ):
        return INVENTORY_CLEANED_CUE
    if kind_text == "state" and monitoring and (
        "模式已启动" in message or message.startswith("监测已启动")
    ):
        return F8_START_CUE
    if (
        kind_text == "state"
        and not monitoring
        and message.startswith("监测已暂停")
    ):
        return F8_STOP_CUE
    if kind_text == "error" or (
        kind_text == "warning" and "紧急停止" in message
    ):
        return CRITICAL_STOP_CUE
    if kind_text == "warning" and any(
        marker in message
        for marker in (
            "识别失败",
            "无法识别",
            "校准失败",
            "无法读取",
            "无法扫描",
            "无法启动后台模式",
        )
    ):
        return RECOGNITION_FAILED_CUE
    return None


def _play_wav(path: Path) -> None:
    if winsound is None:
        return
    winsound.PlaySound(
        str(path),
        winsound.SND_FILENAME | winsound.SND_NODEFAULT,
    )


class VoiceAlertPlayer:
    """单线程串行播放器；相同提示防重入，并按事件设置冷却。"""

    DEFAULT_COOLDOWNS = {
        F7_CALIBRATION_CUE: 1.5,
        F8_START_CUE: 1.0,
        F8_STOP_CUE: 1.0,
        RECOGNITION_FAILED_CUE: 5.0,
        CRITICAL_STOP_CUE: 3.0,
        INVENTORY_CLEANED_CUE: 2.0,
        WINDOW_MINIMIZED_CUE: 1.0,
        WINDOW_RESTORED_CUE: 1.0,
    }
    MAX_PENDING = 2

    def __init__(
        self,
        root: Path = VOICE_DIR,
        *,
        play_file: Callable[[Path], None] = _play_wav,
        clock: Callable[[], float] = time.monotonic,
        choose: Callable[[tuple[Path, ...]], Path] = random.choice,
    ) -> None:
        self._packs = discover_voice_packs(root)
        self._play_file = play_file
        self._clock = clock
        self._choose = choose
        self._enabled = False
        self._character = ""
        self._last_requested: dict[str, float] = {}
        self._pending: deque[tuple[str, Path]] = deque()
        self._active_cue: str | None = None
        self._closed = False
        self._condition = threading.Condition()
        self._thread = threading.Thread(
            target=self._worker,
            name="voice-alert-player",
            daemon=True,
        )
        self._thread.start()

    def available_characters(self) -> tuple[str, ...]:
        return tuple(self._packs)

    def cues_for(self, character: str) -> tuple[str, ...]:
        return tuple(self._packs.get(character, {}))

    def configure(self, enabled: bool, character: str) -> None:
        with self._condition:
            self._enabled = bool(enabled)
            self._character = character if character in self._packs else ""
            if not self._enabled or not self._character:
                self._pending.clear()

    def play(self, cue: str, *, force: bool = False) -> Path | None:
        """排队一个提示；返回选中的音频，忽略重复或缺失时返回 None。"""
        with self._condition:
            if self._closed or not self._enabled or not self._character:
                return None
            variants = self._packs.get(self._character, {}).get(cue, ())
            if not variants:
                return None
            now = self._clock()
            cooldown = self.DEFAULT_COOLDOWNS.get(cue, 1.0)
            if not force and now - self._last_requested.get(cue, float("-inf")) < cooldown:
                return None
            if not force and (
                self._active_cue == cue
                or any(pending_cue == cue for pending_cue, _path in self._pending)
            ):
                return None
            selected = self._choose(variants)
            self._last_requested[cue] = now
            if cue == CRITICAL_STOP_CUE:
                self._pending.clear()
                self._pending.appendleft((cue, selected))
            elif len(self._pending) >= self.MAX_PENDING:
                return None
            else:
                self._pending.append((cue, selected))
            self._condition.notify()
            return selected

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._pending.clear()
            self._condition.notify_all()

    def wait_until_idle(self, timeout: float = 1.0) -> bool:
        """仅供测试和诊断等待，不参与正常 UI 流程。"""
        deadline = time.monotonic() + max(0.0, timeout)
        with self._condition:
            while self._active_cue is not None or self._pending:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(timeout=remaining)
            return True

    def _worker(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                cue, path = self._pending.popleft()
                self._active_cue = cue
            try:
                self._play_file(path)
            except Exception:
                # 语音提醒不能影响钓鱼主流程；缺失设备或损坏 WAV 只静默跳过。
                pass
            finally:
                with self._condition:
                    self._active_cue = None
                    self._condition.notify_all()
