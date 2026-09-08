"""控制台标签页。"""
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

from .base import BasePageMixin
from ..widget.card import Card, MetricCard
from ..widget.controls import ScrollSafeComboBox, ScrollSafeSlider

class DashboardPageMixin(BasePageMixin):
    def _build_dashboard_page(self) -> QScrollArea:
        scroll, layout = BasePageMixin._new_page_canvas()

        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_runtime_card())
        layout.addWidget(self._build_log_card(), 1)

        return scroll

    def _build_profile_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(15)
        layout.addLayout(self._card_heading("游戏画面配置", "记录当前钓鱼画面环境，不会修改游戏或系统设置。"))

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
        key_value.setObjectName("metricValue")
        key_value.setStyleSheet("font-size: 20px; padding: 8px 0;")
        form.addWidget(key_value, 3, 1)
        layout.addLayout(form)

        target = QGridLayout()
        target.setHorizontalSpacing(18)
        target.setVerticalSpacing(10)
        self.target_mode_combo = ScrollSafeComboBox()
        self.target_mode_combo.addItem("指定窗口后台模式（推荐）", "window")
        self.target_mode_combo.addItem("屏幕坐标模式（前台）", "screen")
        self.window_backend_combo = ScrollSafeComboBox()
        self.window_backend_combo.addItem("OK 后台引擎（WGC + PostMessage）", "ok")
        self.window_backend_combo.addItem("兼容引擎（PrintWindow）", "printwindow")
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
        backend_layout = QVBoxLayout(self.backend_options_panel)
        backend_layout.setContentsMargins(14, 13, 14, 14)
        backend_layout.setSpacing(8)
        self.backend_mode_badge = QLabel()
        self.backend_mode_badge.setObjectName("backendModeBadge")
        backend_layout.addWidget(self.backend_mode_badge)
        backend_layout.addWidget(
            self._form_label("后台目标窗口", "优先检测窗口名称“瑪奇 Mobile”；找不到时可手动选择")
        )
        backend_layout.addWidget(target_window_row)
        backend_layout.addWidget(
            self._form_label("后台引擎", "OK 引擎使用 WGC 截图与后台消息；兼容引擎适合排障。")
        )
        backend_layout.addWidget(self.window_backend_combo)

        target.addWidget(
            self._form_label(
                "捕捉与按键模式",
                "推荐后台模式；前台模式依赖当前屏幕画面和真实鼠标",
            ),
            0,
            0,
        )
        target.addWidget(self.target_mode_combo, 1, 0)
        target.addWidget(self.backend_options_panel, 2, 0)
        target.setColumnStretch(0, 1)
        layout.addLayout(target)
        self.target_mode_status = QLabel()
        self.target_mode_status.setObjectName("cardHint")
        self.target_mode_status.setWordWrap(True)
        layout.addWidget(self.target_mode_status)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #263A54;")
        layout.addWidget(divider)

        calibration = QHBoxLayout()
        calibration_text = QVBoxLayout()
        calibration_title = QLabel("按钮校准")
        calibration_title.setObjectName("cardTitle")
        self.calibration_summary = QLabel()
        self.calibration_summary.setObjectName("cardHint")
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
        layout.setContentsMargins(22, 20, 22, 22)
        layout.setSpacing(15)
        layout.addLayout(self._card_heading("运行状态", "识别周期约 75ms，确认后只发送一次按键。"))

        state_row = QHBoxLayout()
        state_text = QVBoxLayout()
        self.runtime_title = QLabel("等待校准")
        self.runtime_title.setObjectName("cardTitle")
        self.runtime_detail = QLabel("将鼠标移动到钓鱼按钮中心。")
        self.runtime_detail.setObjectName("cardHint")
        state_text.addWidget(self.runtime_title)
        state_text.addWidget(self.runtime_detail)
        state_row.addLayout(state_text, 1)
        self.start_button = QPushButton("开始监测")
        self.start_button.setObjectName("primaryButton")
        state_row.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(state_row)

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

        shortcuts = QGridLayout()
        shortcuts.setHorizontalSpacing(9)
        shortcuts.addWidget(MetricCard("校准", "F7"), 0, 0)
        shortcuts.addWidget(MetricCard("开始 / 暂停", "F8"), 0, 1)
        shortcuts.addWidget(MetricCard("保存诊断", "F9"), 0, 2)
        layout.addLayout(shortcuts)
        layout.addStretch(1)

        self.snapshot_status = QLabel("识别不对时按 F9，保存当时的截图和诊断。")
        self.snapshot_status.setObjectName("cardHint")
        self.snapshot_status.setWordWrap(True)
        layout.addWidget(self.snapshot_status)
        debug_row = QHBoxLayout()
        self.snapshot_button = QPushButton("保存识别现场（F9）")
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
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addLayout(self._card_heading("活动记录", "只记录关键状态和上钩事件，方便后续排查。"))
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

    def _build_hardware_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 19, 22, 20)
        layout.setSpacing(10)
        layout.addLayout(
            self._card_heading(
                "本机诊断信息",
                "仅在启动时读取一次，用于本地错误日志的性能判断；不会持续监测或上传。",
            )
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(9)
        self.cpu_model_label = QLabel("正在读取 CPU 型号…")
        self.gpu_model_label = QLabel("正在读取显卡型号…")
        self.memory_model_label = QLabel("正在读取内存型号…")
        for label in (self.cpu_model_label, self.gpu_model_label, self.memory_model_label):
            label.setObjectName("cardHint")
            label.setWordWrap(True)
        for row, (name, value) in enumerate(
            (("CPU", self.cpu_model_label), ("显卡", self.gpu_model_label), ("内存", self.memory_model_label))
        ):
            field = QLabel(name)
            field.setObjectName("formLabel")
            grid.addWidget(field, row, 0)
            grid.addWidget(value, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        return card

