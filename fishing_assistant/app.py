"""桌面应用启动与生命周期管理。"""

from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .constants import APP_ICON_PATH, APP_NAME
from .diagnostics import record_error
from .engine import FishingEngine
from .splash import create_splash
from .startup_guard import prepare_windows_startup
from .ui import MainWindow


def _run_application() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Mabinogi M Fishing Assistant")
    app.setApplicationDisplayName(APP_NAME)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    if APP_ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(APP_ICON_PATH)))

    def handle_unhandled_exception(
        exception_type: type[BaseException], exception: BaseException, traceback: object
    ) -> None:
        record_error("unhandled application exception", exception)
        sys.__excepthook__(exception_type, exception, traceback)

    sys.excepthook = handle_unhandled_exception

    splash = create_splash()
    splash.show()
    app.processEvents()

    engine = FishingEngine()
    window = MainWindow(engine)
    engine.start()
    window.show()

    def finish_startup() -> None:
        splash.finish(window)
        window.begin_startup_services()

    QTimer.singleShot(1100, finish_startup)
    exit_code = app.exec()
    engine.close()
    return exit_code


def main() -> None:
    startup_guard = prepare_windows_startup()
    if startup_guard is None:
        return
    try:
        exit_code = _run_application()
    finally:
        startup_guard.close()
    raise SystemExit(exit_code)
