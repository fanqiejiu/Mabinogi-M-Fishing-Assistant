"""应用身份与打包资源路径。"""

from __future__ import annotations

import sys
from pathlib import Path


APP_NAME = "洛奇 M 钓鱼助手"
APP_VERSION = "0.2.1"
APP_AUTHOR = "番茄啾"
APP_DISPLAY_VERSION = f"{APP_VERSION} by {APP_AUTHOR}"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent


def resource_path(*parts: str) -> Path:
    """兼容源码运行和 PyInstaller onefile 打包后的只读资源目录。"""
    base_dir = Path(getattr(sys, "_MEIPASS", PROJECT_DIR))
    return base_dir.joinpath(*parts)


APP_ICON_PATH = resource_path("fishing_assistant", "assets", "tomato_fish_icon.png")
