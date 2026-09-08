"""识别阈值标签页。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .base import BasePageMixin
from ..widget.card import Card
from ..widget.controls import ScrollSafeComboBox, ScrollSafeSlider

class ThresholdPageMixin(BasePageMixin):
    def _build_threshold_page(self) -> QScrollArea:
        scroll, layout = BasePageMixin._new_page_canvas()

        recognition_card = Card()
        recognition_layout = QVBoxLayout(recognition_card)
        recognition_layout.setContentsMargins(22, 20, 22, 22)
        recognition_layout.setSpacing(15)
        recognition_layout.addLayout(
            self._card_heading(
                "识别引擎",
                "默认使用 OK 框架；旧像素模式作为用户手动选择的兼容方案。",
            )
        )
        self.recognition_backend_combo = ScrollSafeComboBox()
        self.recognition_backend_combo.addItem(
            "OK 框架特征识别（推荐）", "ok"
        )
        self.recognition_backend_combo.addItem(
            "旧版像素识别（兼容）", "pixel"
        )
        recognition_layout.addWidget(
            self._form_label(
                "图标识别模式",
                "两种模式互不回退，切换后立即保存。",
            )
        )
        recognition_layout.addWidget(self.recognition_backend_combo)
        self.recognition_backend_hint = QLabel()
        self.recognition_backend_hint.setObjectName("cardHint")
        self.recognition_backend_hint.setWordWrap(True)
        recognition_layout.addWidget(self.recognition_backend_hint)

        self.threshold_value = QLabel("1200 px")
        self.threshold_value.setObjectName("metricValue")
        self.threshold_slider = ScrollSafeSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(400, 3000)
        self.pixel_fish_threshold_panel = QWidget()
        pixel_threshold_layout = QVBoxLayout(self.pixel_fish_threshold_panel)
        pixel_threshold_layout.setContentsMargins(0, 0, 0, 0)
        pixel_threshold_layout.setSpacing(8)
        threshold_header = QHBoxLayout()
        self.threshold_header_label = self._form_label(
            "旧像素模式：鱼体判定阈值",
            "仅在旧像素识别下生效；OK 模式使用图片特征相似度。",
        )
        threshold_header.addWidget(self.threshold_header_label, 1)
        threshold_header.addWidget(self.threshold_value)
        pixel_threshold_layout.addLayout(threshold_header)
        pixel_threshold_layout.addWidget(self.threshold_slider)
        recognition_layout.addWidget(self.pixel_fish_threshold_panel)
        layout.addWidget(recognition_card)

        region_card = Card()
        region_layout = QVBoxLayout(region_card)
        region_layout.setContentsMargins(22, 20, 22, 22)
        region_layout.setSpacing(14)
        region_layout.addLayout(
            self._card_heading(
                "识别区域与稳定性",
                "自动匹配窗口分辨率；关闭后可以手动调整识别区域。",
            )
        )
        self.auto_roi_check = QCheckBox(
            "自动检测游戏窗口分辨率并调整识别区域（推荐）"
        )
        self.roi_mode_hint = QLabel()
        self.roi_mode_hint.setObjectName("cardHint")
        self.roi_mode_hint.setWordWrap(True)
        region_layout.addWidget(self.auto_roi_check)
        region_layout.addWidget(self.roi_mode_hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        self.roi_width_spin = self._spin_box(100, 640, 160, " px")
        self.roi_height_spin = self._spin_box(100, 720, 180, " px")
        self.interval_combo = ScrollSafeComboBox()
        for value in (50, 75, 100, 125, 150):
            self.interval_combo.addItem(f"{value} ms", value)
        self.trigger_spin = self._spin_box(1, 5, 2, " 帧")
        self.clear_spin = self._spin_box(1, 8, 3, " 帧")
        self.cooldown_spin = self._spin_box(
            300, 2000, 800, " ms"
        )
        self.runtime_retry_spin = self._spin_box(0, 20, 5, " 次")
        controls = [
            (
                "识别区域宽度",
                "应完整覆盖圆形按钮",
                self.roi_width_spin,
            ),
            (
                "识别区域高度",
                "切换分辨率后可微调",
                self.roi_height_spin,
            ),
            ("轮询间隔", "越短反馈越快", self.interval_combo),
            ("触发确认", "连续识别到鱼体才按键", self.trigger_spin),
            ("恢复确认", "图标消失后重新待命", self.clear_spin),
            ("按键冷却", "避免重复发送按键", self.cooldown_spin),
            (
                "临时错误重试",
                "仅用于截图、窗口或识别循环异常",
                self.runtime_retry_spin,
            ),
        ]
        for index, (label, hint, control) in enumerate(controls):
            row = (index // 2) * 2
            column = index % 2
            grid.addWidget(self._form_label(label, hint), row, column)
            grid.addWidget(control, row + 1, column)
            grid.setColumnStretch(column, 1)
        region_layout.addLayout(grid)
        layout.addWidget(region_card)

        pixel_card = Card()
        pixel_layout = QVBoxLayout(pixel_card)
        pixel_layout.setContentsMargins(22, 20, 22, 22)
        pixel_layout.setSpacing(12)
        pixel_layout.addLayout(
            self._card_heading(
                "旧像素模式：指南针范围",
                "仅在旧像素识别下使用；OK 模式会自动禁用这些参数。",
            )
        )
        self.idle_min_spin = self._spin_box(50, 900, 180, " px")
        self.idle_max_spin = self._spin_box(100, 1100, 620, " px")
        pixel_grid = QGridLayout()
        pixel_grid.setHorizontalSpacing(16)
        pixel_grid.addWidget(
            self._form_label("失效指针下限", "红色像素下界"),
            0,
            0,
        )
        pixel_grid.addWidget(
            self._form_label("失效指针上限", "需低于抛竿图标像素数"),
            0,
            1,
        )
        pixel_grid.addWidget(self.idle_min_spin, 1, 0)
        pixel_grid.addWidget(self.idle_max_spin, 1, 1)
        pixel_grid.setColumnStretch(0, 1)
        pixel_grid.setColumnStretch(1, 1)
        pixel_layout.addLayout(pixel_grid)
        layout.addWidget(pixel_card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.restore_button = QPushButton("恢复全部推荐参数")
        actions.addWidget(self.restore_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return scroll
