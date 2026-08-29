"""持久化应用设置；UI 与识别引擎共享这一层，而不彼此耦合。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = APP_DIR / "fishing_config.json"
DEBUG_IMAGE_PATH = APP_DIR / "fishing_roi_debug.png"


@dataclass(slots=True)
class AppConfig:
    """以后新增选项时，在此处加入字段即可自动兼容旧配置文件。"""

    schema_version: int = 6
    button_center: tuple[int, int] | None = None
    monitor_index: int = 1
    display_mode: str = "borderless"
    selected_resolution: str = "1920 × 1080"
    ui_theme: str = "night"
    roi_width: int = 160
    roi_height: int = 180
    poll_interval_ms: int = 75
    # 三张参考图的圆形区域中：失效指针约 365、抛竿约 766、上钩鱼体约 1985。
    fish_red_pixel_threshold: int = 1200
    idle_red_pixel_min: int = 180
    idle_red_pixel_max: int = 620
    trigger_consecutive_frames: int = 2
    clear_consecutive_frames: int = 3
    press_cooldown_ms: int = 800
    auto_resume_fishing: bool = True
    auto_recover_idle: bool = True
    recovery_consecutive_frames: int = 3
    recovery_key_hold_ms: int = 180
    recovery_pause_ms: int = 120
    recovery_cooldown_ms: int = 4500
    recast_delay_ms: int = 650
    # screen：当前稳定模式；window：指定窗口后台模式（实验性）。
    capture_mode: str = "screen"
    # ok：OK 框架的 WGC 截图 + PostMessage；printwindow：旧版兼容实现。
    window_backend: str = "ok"
    target_window_handle: int = 0
    target_window_title: str = ""
    target_button_offset: tuple[int, int] | None = None
    # 默认只用于手动检查；用户可在设置中修改或启用启动时自动检查。
    github_repository: str = "fanqiejiu/Mabinogi-M-Fishing-Assistant"
    github_auto_check: bool = False

    def copy(self, **changes: object) -> "AppConfig":
        return replace(self, **changes)


def default_config() -> AppConfig:
    return AppConfig()


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config()

    # v2 的 90 px 单阈值会把新版的抛竿图标误判成鱼，升级时弃用它。
    if int(raw.get("schema_version", 0)) < 3:
        raw.pop("red_pixel_threshold", None)
        raw["schema_version"] = 3
    if int(raw.get("schema_version", 0)) < 4:
        raw["schema_version"] = 4
    if int(raw.get("schema_version", 0)) < 5:
        raw["schema_version"] = 5
    if int(raw.get("schema_version", 0)) < 6:
        raw["schema_version"] = 6

    valid_names = {field.name for field in fields(AppConfig)}
    values = {name: value for name, value in raw.items() if name in valid_names}
    if values.get("button_center") is not None:
        values["button_center"] = tuple(values["button_center"])
    if values.get("target_button_offset") is not None:
        values["target_button_offset"] = tuple(values["target_button_offset"])
    try:
        return AppConfig(**values)
    except TypeError:
        return default_config()


def save_config(config: AppConfig) -> None:
    data = asdict(config)
    if config.button_center is not None:
        data["button_center"] = list(config.button_center)
    if config.target_button_offset is not None:
        data["target_button_offset"] = list(config.target_button_offset)
    temporary_path = CONFIG_PATH.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(CONFIG_PATH)
