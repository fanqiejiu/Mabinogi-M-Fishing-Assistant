"""可拖动、调透明度的悬浮状态栏。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QStyle, QVBoxLayout, QWidget
from fishing_assistant.desktop.styles import FLOATING_DAY_STYLE, FLOATING_NIGHT_STYLE
from fishing_assistant.desktop.widgets import update_status_label


class FloatingStatusBar(QWidget):
    """后台模式最小化后显示的无焦点、可拖动置顶状态栏。"""

    pause_requested = Signal()
    resume_requested = Signal()

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
        self.setFixedSize(352, 140)
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
        self.runtime_label = QLabel("运行 · 等待校准")
        self.runtime_label.setObjectName("floatingState")
        self.runtime_label.setProperty("state", "idle")
        self.runtime_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        states.addWidget(self.calibration_label, 1)
        states.addWidget(self.runtime_label, 1)
        layout.addLayout(states)

        self.fishing_session_label = QLabel("本次钓鱼 · 上鱼 0 | 普通 0 | 失败 0")
        self.fishing_session_label.setObjectName("floatingHint")
        self.fishing_session_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fishing_session_label.setToolTip(
            "显示本次自动钓鱼的上鱼成功、普通成功和失败次数。"
        )
        layout.addWidget(self.fishing_session_label)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        actions.addStretch(1)
        self.pause_button = QPushButton("暂停")
        self.resume_button = QPushButton("继续")
        self.pause_button.setObjectName("floatingPause")
        self.resume_button.setObjectName("floatingResume")
        self.pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        self.resume_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        for button in (self.pause_button, self.resume_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFixedSize(106, 30)
            button.setIconSize(QSize(14, 14))
            actions.addWidget(button)
        actions.addStretch(1)
        self.pause_button.clicked.connect(self.pause_requested.emit)
        self.resume_button.clicked.connect(self.resume_requested.emit)
        self.pause_button.setToolTip("暂停当前任务。背包整理中会安全停止，不自动继续清理。")
        self.resume_button.setToolTip("继续由暂停按钮暂停的任务；F8 / Esc 停止后不会自动重启。")
        layout.addLayout(actions)
        self.set_task_controls(False, False)

        for label in (
            title,
            hint,
            self.calibration_label,
            self.runtime_label,
            self.fishing_session_label,
        ):
            label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
            )
        self.set_theme("night")

    @staticmethod
    def _refresh_state_label(label: QLabel, state: str, text: str) -> None:
        update_status_label(label, state, text)

    def set_task_controls(self, running: bool, paused: bool) -> None:
        self.pause_button.setEnabled(running and not paused)
        self.resume_button.setEnabled(running and paused)

    def set_calibrated(self, calibrated: bool) -> None:
        self.calibration_label.setToolTip("")
        self._refresh_state_label(
            self.calibration_label,
            "running" if calibrated else "warning",
            "校准 · 已完成" if calibrated else "校准 · 未完成",
        )

    def set_crafting_target(self) -> None:
        self._refresh_state_label(self.calibration_label, "running", "窗口 · 已指定")
        self.calibration_label.setToolTip("自动制作使用开始时选定的游戏窗口，无需 F7 校准。")

    def set_runtime(self, text: str, state: str = "idle") -> None:
        self._refresh_state_label(
            self.runtime_label,
            state,
            f"运行 · {text}",
        )
        self.runtime_label.setToolTip(text)

    def set_fishing_session_stats(
        self, successful: int, ordinary: int, failed: int
    ) -> None:
        self.fishing_session_label.setText(
            f"本次钓鱼 · 上鱼 {successful} | 普通 {ordinary} | 失败 {failed}"
        )

    def set_theme(self, theme: str) -> None:
        self._theme = "day" if theme == "day" else "night"
        self.ensurePolished()
        # 隐藏的工具窗口直接替换 QSS 会残留子控件的旧调色板。
        self.setStyleSheet("")
        self.setStyleSheet(
            FLOATING_DAY_STYLE
            if self._theme == "day"
            else FLOATING_NIGHT_STYLE
        )
        for child in self.findChildren(QWidget):
            child.style().unpolish(child)
            child.style().polish(child)
            child.update()
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
                self.move(
                    area.right() - self.width() - 18,
                    area.top() + 18,
                )
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
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
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
