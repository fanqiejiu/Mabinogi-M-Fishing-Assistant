"""持久化应用设置；UI 与识别引擎共享这一层，而不彼此耦合。"""

from __future__ import annotations

import json
import math
import re
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

_BASE_RESOLUTION = (1920, 1080)
_BASE_ROI_SIZE = (160, 180)
_COMMON_RESOLUTIONS = ((1920, 1080), (2560, 1440), (3840, 2160))
_COMMON_SCALES = (1.0, 4 / 3, 2.0)
_RESOLUTION_PATTERN = re.compile(r"(\d{3,5})\s*[×xX*]\s*(\d{3,5})")


def parse_resolution(value: str) -> tuple[int, int] | None:
    """从 UI 显示文本中提取宽高；兼容乘号和普通 x。"""
    match = _RESOLUTION_PATTERN.search(value)
    if match is None:
        return None
    width, height = int(match.group(1)), int(match.group(2))
    if width <= 0 or height <= 0:
        return None
    return width, height


def resolution_label_for_size(width: int, height: int) -> str:
    """将带边框差值的窗口尺寸归到常见 1080p/2K/4K 档位。"""
    width, height = max(1, int(width)), max(1, int(height))
    for common_width, common_height in _COMMON_RESOLUTIONS:
        relative_error = max(
            abs(width - common_width) / common_width,
            abs(height - common_height) / common_height,
        )
        if relative_error <= 0.06:
            return f"{common_width} × {common_height}"
    return f"{width} × {height}"


def scaled_roi_size(width: int, height: int) -> tuple[int, int]:
    """按画面短边比例缩放 ROI，并吸附常见分辨率以容忍窗口边框。"""
    width, height = max(1, int(width)), max(1, int(height))
    scale = min(width / _BASE_RESOLUTION[0], height / _BASE_RESOLUTION[1])
    for common_scale in _COMMON_SCALES:
        if abs(scale - common_scale) <= 0.07:
            scale = common_scale
            break

    def even_size(base: int, minimum: int, maximum: int) -> int:
        value = int(round((base * scale) / 2) * 2)
        return max(minimum, min(maximum, value))

    return even_size(_BASE_ROI_SIZE[0], 100, 640), even_size(
        _BASE_ROI_SIZE[1], 100, 720
    )


@dataclass(slots=True)
class AppConfig:
    """以后新增选项时，在此处加入字段即可自动兼容旧配置文件。"""

    schema_version: int = 16
    button_center: tuple[int, int] | None = None
    monitor_index: int = 1
    display_mode: str = "borderless"
    selected_resolution: str = "1920 × 1080"
    ui_theme: str = "night"
    roi_width: int = 160
    roi_height: int = 180
    # 默认按实际游戏窗口/所选分辨率缩放；关闭后直接使用上面两个手动值。
    auto_scale_roi: bool = True
    poll_interval_ms: int = 75
    # 临时截图、窗口或识别循环错误最多自动重试次数；0 表示立即暂停。
    runtime_error_retry_count: int = 5
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
    # 连续 W/S 后仍未进入等待上钩状态时停止，避免角色不断移动离开钓鱼区。
    recovery_attempt_limit: int = 5
    # stamina_bounce：体力槽中点灰→绿时收鱼；fixed_delay：按自定义秒数收鱼；instant：上钩即收。
    catch_strategy: str = "stamina_bounce"
    fallback_collect_delay_seconds: float = 5.3
    # 模式二的安全上限；普通鱼约 11 秒消失，默认提前 0.5 秒收杆。
    fixed_delay_latest_collect_seconds: float = 10.5
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
    # 更新源固定为项目仓库；是否在启动时自动检查由用户设置决定。
    github_repository: str = GITHUB_REPOSITORY
    github_auto_check: bool = True
    # 检测 v2 影子模式：并行运行新识别链并记录对照，不参与决策。
    v2_shadow_enabled: bool = False
    # 检测 v2 决策路径：签名层先判（~0.2ms），unknown 帧降级模板仲裁；
    # 读条定位走降采样粗扫+干净锚点模板。关闭即完全回到旧识别路径。
    v2_vision_enabled: bool = True

    def copy(self, **changes: object) -> "AppConfig":
        return replace(self, **changes)


def effective_roi_size(
    config: AppConfig, source_resolution: tuple[int, int] | None = None
) -> tuple[int, int]:
    """返回引擎实际使用的 ROI；手动模式不改写用户配置值。"""
    if not config.auto_scale_roi:
        return max(1, int(config.roi_width)), max(1, int(config.roi_height))
    resolution = source_resolution or parse_resolution(config.selected_resolution)
    if resolution is None:
        resolution = _BASE_RESOLUTION
    return scaled_roi_size(*resolution)


def default_config() -> AppConfig:
    return AppConfig()


def _coerce_point(value: object) -> tuple[int, int] | None:
    """坐标字段只接受两个数字组成的序列；其余结构一律视为未校准。"""
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(
            isinstance(item, (int, float)) and math.isfinite(item)
            for item in value
        )
    ):
        return int(value[0]), int(value[1])
    return None


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return default_config()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default_config()
    if not isinstance(raw, dict):
        return default_config()
    try:
        return _config_from_raw(raw)
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        # 语法正确但结构损坏的配置不应让应用无法启动。
        # OverflowError：json 会把 1e309 解析成 infinity，int(inf) 会抛它。
        return default_config()


def _config_from_raw(raw: dict) -> AppConfig:
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
    if int(raw.get("schema_version", 0)) < 12:
        raw["runtime_error_retry_count"] = 5
        raw["schema_version"] = 12
    if int(raw.get("schema_version", 0)) < 13:
        raw["auto_scale_roi"] = True
        raw["schema_version"] = 13
    if int(raw.get("schema_version", 0)) < 14:
        try:
            raw["fallback_collect_delay_seconds"] = float(
                raw.get("fallback_collect_delay_seconds", 5.3)
            )
        except (TypeError, ValueError):
            raw["fallback_collect_delay_seconds"] = 5.3
        raw["schema_version"] = 14
    if int(raw.get("schema_version", 0)) < 15:
        raw["fixed_delay_latest_collect_seconds"] = 10.5
        raw["schema_version"] = 15
    if int(raw.get("schema_version", 0)) < 16:
        raw["recovery_attempt_limit"] = 5
        raw["schema_version"] = 16
    try:
        raw["fallback_collect_delay_seconds"] = float(
            raw.get("fallback_collect_delay_seconds", 5.3)
        )
    except (TypeError, ValueError):
        raw["fallback_collect_delay_seconds"] = 5.3
    try:
        latest_collect = float(
            raw.get("fixed_delay_latest_collect_seconds", 10.5)
        )
        raw["fixed_delay_latest_collect_seconds"] = (
            latest_collect
            if math.isfinite(latest_collect) and 0.1 <= latest_collect <= 60.0
            else 10.5
        )
    except (TypeError, ValueError):
        raw["fixed_delay_latest_collect_seconds"] = 10.5
    try:
        raw["recovery_attempt_limit"] = max(
            1, min(20, int(raw.get("recovery_attempt_limit", 5)))
        )
    except (TypeError, ValueError, OverflowError):
        raw["recovery_attempt_limit"] = 5
    if raw.get("recognition_backend") not in {"ok", "pixel"}:
        raw["recognition_backend"] = "ok"
    # 更新源始终固定在项目自身仓库；是否启动时检查由用户设置决定。
    raw["github_repository"] = GITHUB_REPOSITORY
    raw["github_auto_check"] = bool(raw.get("github_auto_check", True))

    valid_names = {field.name for field in fields(AppConfig)}
    values = {name: value for name, value in raw.items() if name in valid_names}
    values["button_center"] = _coerce_point(values.get("button_center"))
    values["target_button_offset"] = _coerce_point(
        values.get("target_button_offset")
    )
    return AppConfig(**values)


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
