"""应用启动时短暂展示的品牌页。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from .constants import APP_AUTHOR, APP_ICON_PATH, APP_VERSION


def create_splash() -> QSplashScreen:
    canvas = QPixmap(560, 320)
    canvas.fill(QColor("#09111F"))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#7F9BBC"))
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
    painter.drawText(42, 46, "MABINOGI M · FISHING ASSISTANT")

    icon = QPixmap(str(APP_ICON_PATH))
    if not icon.isNull():
        scaled = icon.scaled(
            136,
            136,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(42, 83, scaled)

    painter.setPen(QColor("#F7FAFC"))
    painter.setFont(QFont("Microsoft YaHei UI", 24, QFont.Weight.Bold))
    painter.drawText(205, 142, "洛奇 M 钓鱼助手")
    painter.setPen(QColor("#80E7BF"))
    painter.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
    painter.drawText(207, 177, f"v{APP_VERSION}  ·  by {APP_AUTHOR}")
    painter.setPen(QColor("#8296B0"))
    painter.setFont(QFont("Microsoft YaHei UI", 10))
    painter.drawText(207, 210, "正在准备本地识别与诊断环境…")
    painter.end()

    splash = QSplashScreen(canvas)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    return splash
