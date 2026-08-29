"""应用身份与打包资源路径。"""

from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "洛奇 M 钓鱼助手"
APP_VERSION = "0.5.3.1"
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
FISH_ESCAPE_TEMPLATE_PATH = resource_path(
    "fishing_assistant", "assets", "fish_escaped_text.png"
)
