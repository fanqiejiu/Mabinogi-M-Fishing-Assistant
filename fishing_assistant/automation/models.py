"""引擎事件、识别状态和观测数据；不导入 UI 或启动引擎。"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class EventKind(str, Enum):
    PAUSE = "pause"
    CRAFTING = "crafting"
    FISHING_SESSION_STATS = "fishing_session_stats"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    METRIC = "metric"
    CONFIG = "config"
    STATE = "state"
    DIAGNOSTIC = "diagnostic"

class FishingResult(str, Enum):
    """One resolved fishing round."""

    CATCH = "catch"
    ORDINARY = "ordinary"
    FAILURE = "failure"

class IconState(str, Enum):
    NORMAL = "normal"
    READY_TO_CAST = "ready_to_cast"
    WAITING_BITE = "waiting_bite"
    FISH_HOOKED = "fish_hooked"
    IDLE_RECOVERY = "idle_recovery"
    HORSE_MOUNT_PROMPT = "horse_mount_prompt"
    HORSE_DISMOUNT_PROMPT = "horse_dismount_prompt"

class StaminaMidpointState(str, Enum):
    """体力槽半条位置采样块的颜色状态。"""

    UNKNOWN = "unknown"
    GREEN = "green"
    DARK = "dark"

class _OperationCancelled(RuntimeError):
    """本轮工作已被暂停或被新一轮运行替代。"""

class _CleanupCancelled(_OperationCancelled):
    """用户在背包整理途中暂停了监测。"""

@dataclass(frozen=True, slots=True)
class IconColorSignals:
    red_pixels: int
    red_ratio: float
    white_ratio: float
    green_ratio: float
    blue_ratio: float
    brown_ratio: float
    recognition_source: str = "compat_pixel"
    recognition_confidence: float = 0.0

@dataclass(frozen=True, slots=True)
class StaminaBarSample:
    """动态体力条的一次观测，并记录半条位置的局部颜色。"""

    fill_width: int
    center: tuple[int, int]
    anchor_confidence: float = 1.0
    fill_left: int | None = None
    fill_height: int = 0
    midpoint_state: StaminaMidpointState = StaminaMidpointState.UNKNOWN
    midpoint_green_ratio: float = 0.0
    midpoint_dark_ratio: float = 0.0

@dataclass(slots=True)
class EngineEvent:
    kind: EventKind
    message: str
    red_pixels: int = 0
    recognition_source: str = ""
    recognition_confidence: float = 0.0
    fish_visible: bool = False
    monitoring: bool = False
    icon_state: IconState = IconState.NORMAL
    debug_image: Path | None = None
    stamina_fill_width: int = 0
    stamina_peak_width: int = 0
    waiting_for_bounce: bool = False
    catch_strategy: str = ""
    hook_elapsed_seconds: float = 0.0
    diagnostic_path: Path | None = None
    snapshot_state: str = ""
    crafting: object | None = None
    crafting_log: bool = False
    fishing_session_id: int = 0
    successful_fishing_count: int = 0
    ordinary_fishing_count: int = 0
    failed_fishing_count: int = 0

EventCallback = Callable[[EngineEvent], None]
