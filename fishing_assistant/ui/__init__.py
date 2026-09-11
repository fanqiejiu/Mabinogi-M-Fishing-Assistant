"""桌面界面包，对外提供主窗口及兼容的 UI 导出。"""

from PySide6.QtGui import QDesktopServices

from ..diagnostics import record_error
from ..updates import check_github_release
from .main_window import *
