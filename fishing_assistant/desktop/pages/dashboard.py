"""控制台页面：窗口选择、运行指标和日志布局"""
from __future__ import annotations
from fishing_assistant.desktop.design import configure_card_layout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from fishing_assistant.desktop.widgets import Card, DetailsPanel, MetricCard, ScrollSafeComboBox, ScrollSafeSlider
from fishing_assistant.desktop.terminology import (
    RUN_MODE_LABELS, WINDOW_CAPTURE_LABELS, WINDOW_CAPTURE_DESCRIPTIONS,
    WINDOW_INPUT_LABEL, WINDOW_INPUT_DESCRIPTION,
)


class DashboardPageMixin:
    """控制台页面：窗口选择、运行指标和日志布局；由 MainWindow 组装，不单独实例化。"""

    def _build_dashboard_page(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn
        )
        canvas = QWidget()
        canvas.setObjectName("pageCanvas")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 9, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_runtime_card())
        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_log_card(), 1)
        layout.addWidget(self._build_detection_status_card())

        scroll.setWidget(canvas)
        return scroll

    def _build_profile_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.setSpacing(15)
        layout.addLayout(self._card_heading("游戏窗口"))

        form = QGridLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(14)
        self.monitor_combo = ScrollSafeComboBox()
        self.mode_combo = ScrollSafeComboBox()
        self.mode_combo.addItem("无边框全屏（推荐）", "borderless")
        self.mode_combo.addItem("独占全屏", "fullscreen")
        self.mode_combo.addItem("窗口模式", "windowed")
        self.resolution_combo = ScrollSafeComboBox()
        form.addWidget(self._form_label("目标显示器", "选择游戏所在的屏幕"), 0, 0)
        form.addWidget(self.monitor_combo, 1, 0)
        form.addWidget(self._form_label("画面模式", "用于保存当前游戏配置"), 0, 1)
        form.addWidget(self.mode_combo, 1, 1)
        form.addWidget(
            self._form_label("游戏分辨率", "自动检测开启时由游戏窗口选择，也可关闭后手动指定"),
            2,
            0,
        )
        form.addWidget(self.resolution_combo, 3, 0)
        form.addWidget(self._form_label("操作按键", "上钩时向所选目标发送"), 2, 1)
        key_value = QLabel("Space")
        key_value.setObjectName("shortcutKey")
        form.addWidget(key_value, 3, 1)
        self.profile_details = DetailsPanel("画面配置", ())
        self.profile_details.setToolTip("调整显示器、画面模式与分辨率；后台模式默认自动匹配。")
        self.profile_details.content.layout().addLayout(form)

        target = QGridLayout()
        target.setHorizontalSpacing(18)
        target.setVerticalSpacing(10)
        self.target_mode_combo = ScrollSafeComboBox()
        for value, label in RUN_MODE_LABELS.items():
            self.target_mode_combo.addItem(label, value)
        self.window_backend_combo = ScrollSafeComboBox()
        for value, label in WINDOW_CAPTURE_LABELS.items():
            self.window_backend_combo.addItem(label, value)
            self.window_backend_combo.setItemData(
                self.window_backend_combo.count() - 1, WINDOW_CAPTURE_DESCRIPTIONS[value],
                Qt.ItemDataRole.ToolTipRole,
            )
        self.target_window_combo = ScrollSafeComboBox()
        self.refresh_windows_button = QPushButton("刷新窗口")
        target_window_row = QWidget()
        target_window_layout = QHBoxLayout(target_window_row)
        target_window_layout.setContentsMargins(0, 0, 0, 0)
        target_window_layout.setSpacing(8)
        target_window_layout.addWidget(self.target_window_combo, 1)
        target_window_layout.addWidget(self.refresh_windows_button)

        self.backend_options_panel = QFrame()
        self.backend_options_panel.setObjectName("backendOptions")
        backend_layout = QGridLayout(self.backend_options_panel)
        backend_layout.setContentsMargins(14, 13, 14, 14)
        backend_layout.setSpacing(8)
        self.backend_mode_badge = QLabel()
        self.backend_mode_badge.setObjectName("backendModeBadge")
        backend_layout.addWidget(self.backend_mode_badge, 0, 0, 1, 2)
        backend_layout.addWidget(
            self._form_label("目标窗口", "优先检测窗口名称“瑪奇 Mobile”；找不到时可手动选择"), 1, 0
        )
        backend_layout.addWidget(target_window_row, 1, 1)
        backend_layout.addWidget(
            self._form_label("捕获方式", "选择目标窗口的画面获取方式，不影响图标识别算法或输入方式。"), 2, 0
        )
        backend_layout.addWidget(self.window_backend_combo, 2, 1)
        backend_layout.addWidget(self._form_label("输入方式", WINDOW_INPUT_DESCRIPTION), 3, 0)
        self.window_input_label = QLabel(WINDOW_INPUT_LABEL)
        self.window_input_label.setObjectName("helper")
        self.window_input_label.setWordWrap(True)
        self.window_input_label.setToolTip(WINDOW_INPUT_DESCRIPTION)
        backend_layout.addWidget(self.window_input_label, 3, 1)
        backend_layout.setColumnStretch(1, 1)

        target.addWidget(
            self._form_label(
                "运行方式",
                "推荐后台模式；前台模式依赖当前屏幕画面和真实鼠标",
            ),
            0,
            0,
        )
        target.addWidget(self.target_mode_combo, 0, 1)
        target.addWidget(self.backend_options_panel, 1, 0, 1, 2)
        target.setColumnStretch(1, 1)
        layout.addLayout(target)
        self.target_mode_status = QLabel()
        self.target_mode_status.setObjectName("cardHint")
        self.target_mode_status.setWordWrap(True)
        layout.addWidget(self.target_mode_status)
        layout.addWidget(self.profile_details)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("sectionDivider")
        layout.addWidget(divider)

        calibration = QHBoxLayout()
        calibration_text = QVBoxLayout()
        calibration_title = QLabel("按钮校准")
        calibration_title.setObjectName("cardTitle")
        self.calibration_summary = QLabel()
        self.calibration_summary.setObjectName("cardHint")
        self.calibration_summary.setWordWrap(True)
        calibration_text.addWidget(calibration_title)
        calibration_text.addWidget(self.calibration_summary)
        self.calibrate_button = QPushButton("使用 F7 校准")
        self.calibrate_button.setToolTip("将鼠标停在钓鱼按钮中心后按 F7；此按钮不会记录当前助手窗口的位置。")
        calibration.addLayout(calibration_text, 1)
        calibration.addWidget(self.calibrate_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(calibration)
        return card

    def _build_runtime_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.setSpacing(15)
        layout.addLayout(self._card_heading("运行状态"))

        state_row = QHBoxLayout()
        state_text = QVBoxLayout()
        self.runtime_title = QLabel("等待校准")
        self.runtime_title.setObjectName("cardTitle")
        self.runtime_detail = QLabel("将鼠标移动到钓鱼按钮中心。")
        self.runtime_detail.setObjectName("cardHint")
        self.runtime_detail.setWordWrap(True)
        state_text.addWidget(self.runtime_title)
        state_text.addWidget(self.runtime_detail)
        state_row.addLayout(state_text, 1)
        self.start_button = QPushButton("开始监测")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setMinimumWidth(132)
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        state_row.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(state_row)

        shortcuts = QLabel("F7  校准    ·    F8  开始 / 停止    ·    F9  保存现场")
        shortcuts.setObjectName("helper")
        shortcuts.setWordWrap(True)
        layout.addWidget(shortcuts)

        layout.addLayout(self._card_heading("本次钓鱼"))
        fishing_counts = QGridLayout()
        fishing_counts.setHorizontalSpacing(8)
        self.fishing_success_metric = MetricCard("上鱼成功", "0 次")
        self.fishing_ordinary_metric = MetricCard("普通成功", "0 次")
        self.fishing_failure_metric = MetricCard("失败钓鱼", "0 次")
        self.fishing_success_metric.setToolTip(
            "本次自动钓鱼中按下钓鱼键后，进度条清空的次数。"
        )
        self.fishing_ordinary_metric.setToolTip(
            "本次自动钓鱼中未检测到回弹、进度条自然流失清空的次数。"
        )
        self.fishing_failure_metric.setToolTip(
            "本次自动钓鱼中检测到回弹后，进度条重新涨满并消失的次数。"
        )
        fishing_counts.addWidget(self.fishing_success_metric, 0, 0)
        fishing_counts.addWidget(self.fishing_ordinary_metric, 0, 1)
        fishing_counts.addWidget(self.fishing_failure_metric, 0, 2)
        layout.addLayout(fishing_counts)
        return card

    def _build_detection_status_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.setSpacing(12)
        layout.addLayout(self._card_heading("识别与诊断"))

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(12)
        self.red_metric = MetricCard("当前红色像素", "0 px")
        self.stamina_metric = MetricCard("活鱼体力条", "等待上钩")
        metrics.addWidget(self.red_metric, 0, 0)
        metrics.addWidget(self.stamina_metric, 0, 1)
        layout.addLayout(metrics)
        self.red_progress = ScrollSafeSlider(Qt.Orientation.Horizontal)
        self.red_progress.setEnabled(False)
        self.red_progress.setMinimum(0)
        self.red_progress.setMaximum(1200)
        layout.addWidget(self.red_progress)
        self.stamina_progress = QProgressBar()
        self.stamina_progress.setRange(0, 100)
        self.stamina_progress.setValue(0)
        self.stamina_progress.setTextVisible(False)
        layout.addWidget(self.stamina_progress)

        self.snapshot_status = QLabel("F9 保存识别现场")
        self.snapshot_status.setObjectName("cardHint")
        self.snapshot_status.setWordWrap(True)
        layout.addWidget(self.snapshot_status)
        debug_row = QHBoxLayout()
        self.snapshot_button = QPushButton("保存现场（F9）")
        self.snapshot_button.setToolTip("先按 F7 校准；保存截图和诊断，不会开始钓鱼或自动上传。")
        self.view_snapshot_button = QPushButton("查看截图")
        self.view_snapshot_button.setEnabled(False)
        self.open_snapshot_folder_button = QPushButton("打开诊断目录")
        debug_row.addWidget(self.snapshot_button)
        debug_row.addWidget(self.view_snapshot_button)
        debug_row.addWidget(self.open_snapshot_folder_button)
        debug_row.addStretch(1)
        layout.addLayout(debug_row)
        return card

    def _build_log_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addLayout(self._card_heading("运行日志"))
        header.addStretch(1)
        clear_button = QPushButton("清空")
        clear_button.clicked.connect(lambda: self.log_view.clear())
        header.addWidget(clear_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(header)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.document().setMaximumBlockCount(220)
        self.log_view.setMinimumHeight(175)
        layout.addWidget(self.log_view)
        return card
