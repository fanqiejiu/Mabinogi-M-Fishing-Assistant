"""持久化应用设置；UI 与识别引擎共享这一层，而不彼此耦合。"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

from .constants import GITHUB_REPOSITORY


APP_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
CONFIG_PATH = APP_DIR / "fishing_config.json"
DEBUG_IMAGE_PATH = APP_DIR / "fishing_roi_debug.png"


@dataclass(slots=True)
class AppConfig:
    """以后新增选项时，在此处加入字段即可自动兼容旧配置文件。"""

    schema_version: int = 11
    button_center: tuple[int, int] | None = None
    monitor_index: int = 1
    display_mode: str = "borderless"
    selected_resolution: str = "1920 × 1080"
    ui_theme: str = "night"
    roi_width: int = 160
    roi_height: int = 180
    poll_interval_ms: int = 75
    # ok：OK FeatureSet 图片特征识别（默认）；pixel：旧版颜色/像素兼容识别。
    # 两种模式由用户明确选择，OK 模式不会自动回退到像素规则。
    recognition_backend: str = "ok"
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
    # stamina_bounce：角色头顶绿条反弹时收鱼；fixed_delay：按自定义秒数收鱼；instant：上钩即收。
    catch_strategy: str = "stamina_bounce"
    fallback_collect_delay_seconds: int = 14
    stamina_scan_interval_ms: int = 60
    stamina_zoom_in_steps: int = 5
    # 模式一检测到跑鱼提示后记录本次上钩持续时间，供下一次计时兜底。
    learned_escape_seconds: float = 0.0
    # screen：当前稳定模式；window：指定窗口后台模式（实验性）。
    capture_mode: str = "screen"
    # ok：OK 框架的 WGC 截图 + PostMessage；printwindow：旧版兼容实现。
    window_backend: str = "ok"
    target_window_handle: int = 0
    target_window_title: str = ""
    target_button_offset: tuple[int, int] | None = None
    # 更新源固定为项目仓库，并在每次启动后自动检查 Latest Release。
    github_repository: str = GITHUB_REPOSITORY
    github_auto_check: bool = True

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
    if int(raw.get("schema_version", 0)) < 7:
        raw["schema_version"] = 7
    if int(raw.get("schema_version", 0)) < 8:
        raw["schema_version"] = 8
    if int(raw.get("schema_version", 0)) < 9:
        raw["schema_version"] = 9
    if int(raw.get("schema_version", 0)) < 10:
        raw["learned_escape_seconds"] = 0.0
        raw["schema_version"] = 10
    if int(raw.get("schema_version", 0)) < 11:
        # 升级后明确使用新的默认方案；不把旧像素规则偷偷混入 OK 模式。
        raw["recognition_backend"] = "ok"
        raw["schema_version"] = 11
    if raw.get("recognition_backend") not in {"ok", "pixel"}:
        raw["recognition_backend"] = "ok"
    # 不受旧配置影响，更新源始终固定在项目自身仓库并默认启用启动检查。
    raw["github_repository"] = GITHUB_REPOSITORY
    raw["github_auto_check"] = True

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
