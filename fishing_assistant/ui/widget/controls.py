"""不拦截页面滚动的输入控件和后台悬浮状态栏。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from ..styles.theme import FLOATING_DAY_STYLE, FLOATING_NIGHT_STYLE


class ScrollSafeSpinBox(QSpinBox):
    """滚轮用于滚动页面，避免鼠标经过数值框时意外改值。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class ScrollSafeDoubleSpinBox(QDoubleSpinBox):
    """小数输入框同样把滚轮交给外层页面。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class ScrollSafeComboBox(QComboBox):
    """下拉列表关闭时把滚轮交给页面，避免经过选项框时误切换。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class ScrollSafeSlider(QSlider):
    """滑条仅响应拖动和键盘，不拦截页面滚动。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class FloatingStatusBar(QWidget):
    """后台模式最小化后显示的无焦点、可拖动置顶状态栏。"""

    def __init__(self) -> None:
        super().__init__(None)
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setObjectName("floatingStatus")
        self.setWindowTitle("洛奇 M 钓鱼助手 · 后台状态")
        self.setFixedSize(352, 82)
        self._drag_offset = None
        self._positioned = False
        self._theme = "night"
        self._background_opacity = 92

        layout = QVBoxLayout(self)
        layout.setContentsMargins(13, 9, 13, 11)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(8)
        title = QLabel("洛奇 M 钓鱼助手")
        title.setObjectName("floatingTitle")
        hint = QLabel("后台状态 · 可拖动")
        hint.setObjectName("floatingHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(hint)
        layout.addLayout(header)

        states = QHBoxLayout()
        states.setSpacing(8)
        self.calibration_label = QLabel("校准 · 未完成")
        self.calibration_label.setObjectName("floatingState")
        self.calibration_label.setProperty("state", "warning")
        self.calibration_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.calibration_label.setFixedWidth(118)
        self.runtime_label = QLabel("运行 · 等待校准")
        self.runtime_label.setObjectName("floatingState")
        self.runtime_label.setProperty("state", "idle")
        self.runtime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        states.addWidget(self.calibration_label)
        states.addWidget(self.runtime_label, 1)
        layout.addLayout(states)

        for label in (title, hint, self.calibration_label, self.runtime_label):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_theme("night")

    @staticmethod
    def _refresh_state_label(label: QLabel, state: str, text: str) -> None:
        label.setProperty("state", state)
        label.setText(text)
        label.style().unpolish(label)
        label.style().polish(label)

    def set_calibrated(self, calibrated: bool) -> None:
        self._refresh_state_label(
            self.calibration_label,
            "running" if calibrated else "warning",
            "校准 · 已完成" if calibrated else "校准 · 未完成",
        )

    def set_runtime(self, text: str, state: str = "idle") -> None:
        self._refresh_state_label(self.runtime_label, state, f"运行 · {text}")
        self.runtime_label.setToolTip(text)

    def set_theme(self, theme: str) -> None:
        self._theme = "day" if theme == "day" else "night"
        self.setStyleSheet(
            FLOATING_DAY_STYLE if self._theme == "day" else FLOATING_NIGHT_STYLE
        )
        self.update()

    def set_background_opacity(self, value: int) -> None:
        self._background_opacity = max(35, min(100, int(value)))
        self.update()

    def background_opacity(self) -> int:
        return self._background_opacity

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        background = QColor("#EDF4FA" if self._theme == "day" else "#09111F")
        background.setAlpha(round(255 * self._background_opacity / 100))
        border = QColor("#91A9C1" if self._theme == "day" else "#34506F")
        painter.setPen(QPen(border, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 13, 13)

    def show_at_default_position(self) -> None:
        if not self._positioned:
            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(area.right() - self.width() - 18, area.top() + 18)
            self._positioned = True
        self.show()
        self.raise_()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._positioned = True
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
