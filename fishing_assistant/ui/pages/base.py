"""标签页的公共构建能力。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QLabel,
    QWidget,
)

from ..widget.card import card_heading, form_label


class BasePageMixin:
    """为页面 Mixin 提供统一的滚动容器和常用布局辅助。"""

    @staticmethod
    def _new_page_canvas() -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        canvas = QWidget()
        canvas.setObjectName("pageCanvas")
        canvas.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        canvas.setMinimumWidth(0)
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 9, 0)
        layout.setSpacing(16)
        scroll.setWidget(canvas)
        return scroll, layout

    @staticmethod
    def _card_heading(title: str, hint: str = "") -> QVBoxLayout:
        return card_heading(title, hint)

    @staticmethod
    def _form_label(title: str, hint: str) -> QWidget:
        return form_label(title, hint)
