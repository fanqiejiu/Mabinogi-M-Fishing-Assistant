"""应用身份与打包资源路径。"""

from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "洛奇 M 钓鱼助手"
APP_VERSION = "0.5.7.3"
APP_AUTHOR = "番茄啾"
APP_DISPLAY_VERSION = APP_VERSION
GITHUB_REPOSITORY = "fanqiejiu/Mabinogi-M-Fishing-Assistant"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent


def resource_path(*parts: str) -> Path:
    """兼容源码运行和 PyInstaller onefile 打包后的只读资源目录。"""
    base_dir = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
    return base_dir.joinpath(*parts)


APP_ICON_PATH = resource_path("fishing_assistant", "assets", "tomato_fish_icon.png")
OK_IDLE_MOTION_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "ok_icon_idle_recovery_motion.gif"
)
OK_STAMINA_ANCHOR_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "ok_stamina_fish_anchor.png"
)
OK_ICON_TEMPLATE_PATHS = {
    "waiting_bite": resource_path(
        "fishing_assistant", "assets", "ok_icon_waiting_bite.png"
    ),
    "fish_hooked": resource_path(
        "fishing_assistant", "assets", "ok_icon_fish_hooked.png"
    ),
    "ready_to_cast": resource_path(
        "fishing_assistant", "assets", "ok_icon_ready_to_cast.png"
    ),
    "idle_recovery": resource_path(
        "fishing_assistant", "assets", "ok_icon_idle_recovery.png"
    ),
    "horse_mount_prompt": resource_path(
        "fishing_assistant", "assets", "ok_icon_horse_mount.png"
    ),
    "horse_dismount_prompt": resource_path(
        "fishing_assistant", "assets", "ok_icon_horse_dismount.png"
    ),
}
FISH_ESCAPE_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "fish_escaped_text.png"
)
INVENTORY_FULL_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "inventory_full_text.png"
)
INVENTORY_FULL_ICON_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "inventory_full_icon.png"
)
ROD_REQUIRED_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "rod_required_text.png"
)
