"""通用卡片和防滚轮误改控件，不依赖主窗口。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QLabel,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def update_status_label(label: QLabel, state: str, text: str) -> None:
    """状态未变化时不重新应用 QSS，避免高频监测反复触发布局刷新。"""
    changed = label.property("state") != state
    if changed:
        label.setProperty("state", state)
    if label.text() != text:
        label.setText(text)
    if changed:
        label.style().unpolish(label)
        label.style().polish(label)


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )


class DetailsPanel(QWidget):
    """默认收起的补充说明；危险告知须放在本控件外，保持直接可见。"""

    def __init__(self, title: str, paragraphs: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = QToolButton()
        self.toggle.setObjectName("detailsToggle")
        self.toggle.setText(title)
        self.toggle.setAccessibleName(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignLeft)
        self.content = QWidget()
        body = QVBoxLayout(self.content)
        body.setContentsMargins(18, 0, 0, 0)
        body.setSpacing(6)
        for text in paragraphs:
            label = QLabel(text)
            label.setObjectName("helper")
            label.setWordWrap(True)
            body.addWidget(label)
        self.content.setVisible(False)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._set_expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)

class MetricCard(QFrame):
    def __init__(self, caption: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(3)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("metricCaption")
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption_label)

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


class ScrollSafeTabBar(QTabBar):
    """页内分类只响应点击与键盘，滚轮经过时不切换页面。"""

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()
