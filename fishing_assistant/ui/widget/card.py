"""可复用的页面卡片组件。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class Card(QFrame):
    """带统一卡片样式标识的容器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


class MetricCard(QFrame):
    """展示一个指标值及其说明的卡片。"""

    def __init__(
        self,
        caption: str,
        value: str,
        parent: QWidget | None = None,
    ) -> None:
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


def card_heading(title: str, hint: str = "") -> QVBoxLayout:
    """创建卡片标题及可选说明。"""

    layout = QVBoxLayout()
    layout.setSpacing(3)
    title_label = QLabel(title)
    title_label.setObjectName("cardTitle")
    layout.addWidget(title_label)
    if hint:
        hint_label = QLabel(hint)
        hint_label.setObjectName("cardHint")
        hint_label.setWordWrap(True)
        layout.addWidget(hint_label)
    return layout


def form_label(title: str, hint: str) -> QWidget:
    """创建表单字段标题及说明。"""

    widget = QWidget()
    widget.setSizePolicy(
        QSizePolicy.Policy.Ignored,
        QSizePolicy.Policy.Preferred,
    )
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("formLabel")
    title_label.setWordWrap(True)
    hint_label = QLabel(hint)
    hint_label.setObjectName("helper")
    hint_label.setWordWrap(True)
    layout.addWidget(title_label)
    layout.addWidget(hint_label)
    return widget
