"""Qt 桌面界面。所有业务操作由 FishingEngine 完成，UI 只负责呈现和配置。"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QLocale, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QIcon,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import window_target
from ..constants import (
    APP_AUTHOR,
    APP_DISPLAY_VERSION,
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    GITHUB_REPOSITORY,
)
from ..diagnostics import (
    set_system_profile,
)
from ..engine import EngineEvent, EventKind, FishingEngine, IconState
from ..system_profile import SystemProfile, collect_system_profile
from .configuration import ConfigurationMixin
from .services import WindowServicesMixin
from .styles.theme import DAY_STYLE, NIGHT_STYLE
from .widget.controls import (
    FloatingStatusBar,
    ScrollSafeComboBox,
    ScrollSafeDoubleSpinBox,
    ScrollSafeSlider,
    ScrollSafeSpinBox,
)
from .widget.dialogs import (
    InventoryCleanupTestDialog,
    InventoryCleanupWarningDialog,
    UpdateAvailableDialog,
    WOnlyModeWarningDialog,
)
from .pages.dashboard import DashboardPageMixin
from .pages.fishing import FishingPageMixin
from .pages.help import HelpPageMixin
from .pages.settings import SettingsPageMixin
from .pages.threshold import ThresholdPageMixin
from ..voice_alerts import (
    F7_CALIBRATION_CUE,
    F8_STOP_CUE,
    WINDOW_MINIMIZED_CUE,
    WINDOW_RESTORED_CUE,
    VoiceAlertPlayer,
    cue_for_engine_event,
)


class MainWindow(
    ConfigurationMixin,
    WindowServicesMixin,
    DashboardPageMixin,
    FishingPageMixin,
    ThresholdPageMixin,
    SettingsPageMixin,
    HelpPageMixin,
    QMainWindow,
):
    """配置中心、运行状态与操作日志组成的单窗口桌面应用。"""

    PAGE_META = (
        ("LOCAL AUTOMATION · OVERVIEW", "钓鱼控制台", "校准、启动和运行状态集中在这里。"),
        ("FISHING · BEHAVIOR", "钓鱼设置", "设置收鱼方式、自动续钓和指南针恢复。"),
        ("DETECTION · TUNING", "识别阈值", "调整识别引擎、区域和兼容模式阈值。"),
        ("APPLICATION · SETTINGS", "应用设置", "管理更新检查与本地诊断日志。"),
        ("GUIDE · HOTKEYS", "使用说明", "查看校准流程和全局快捷键。"),
    )

    engine_event = Signal(object)
    profile_ready = Signal(object)
    update_ready = Signal(object)

    def __init__(self, engine: FishingEngine) -> None:
        super().__init__()
        self.engine = engine
        self.voice_player = VoiceAlertPlayer()
        self.engine.set_event_callback(self.engine_event.emit)
        self.engine_event.connect(self._consume_engine_event)
        self.profile_ready.connect(self._show_system_profile)
        self.update_ready.connect(self._show_update_result)
        self._navigation: list[QPushButton] = []
        self._last_release_url: str | None = None
        self._notified_release_version: str | None = None
        self._update_dialog: UpdateAvailableDialog | None = None
        self._auto_detected_game_window: window_target.WindowInfo | None = None
        self._last_snapshot_path: Path | None = None
        self._last_snapshot_bundle: Path | None = None
        self.floating_status_bar = FloatingStatusBar()

        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setMinimumSize(760, 680)
        self.resize(980, 760)
        self.setStyleSheet(NIGHT_STYLE)

        self._build_shell()
        self._populate_display_options()
        self._load_config(self.engine.config())
        self._connect_controls()
        self._apply_theme(self.engine.config().ui_theme)
        self._refresh_calibration_summary()
        self._append_log("界面已准备就绪，等待完成按钮校准。", EventKind.INFO)

    def _build_shell(self) -> None:
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        content = QFrame()
        content.setObjectName("contentSurface")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 22, 22, 24)
        content_layout.setSpacing(16)
        content_layout.addLayout(self._build_topbar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_dashboard_page())
        self.stack.addWidget(self._build_detection_page())
        self.stack.addWidget(self._build_threshold_page())
        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_help_page())
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(202)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 20)
        layout.setSpacing(7)

        brand_row = QHBoxLayout()
        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(48, 48)
        icon = QPixmap(str(APP_ICON_PATH))
        if not icon.isNull():
            mark.setPixmap(
                icon.scaled(
                    48,
                    48,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_text = QVBoxLayout()
        title = QLabel("洛奇 M 钓鱼助手")
        title.setObjectName("brandTitle")
        subtitle = QLabel("FISHING ASSISTANT")
        subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_text.setSpacing(1)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(31)

        layout.addWidget(self._nav_button("控制台", 0, True))
        layout.addWidget(self._nav_button("钓鱼设置", 1))
        layout.addWidget(self._nav_button("识别阈值", 2))
        layout.addWidget(self._nav_button("设置", 3))
        layout.addWidget(self._nav_button("使用说明", 4))
        layout.addStretch(1)

        footer = QLabel(f"v{APP_VERSION}  ·  {APP_AUTHOR}")
        footer.setObjectName("brandSubtitle")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        return sidebar

    def _nav_button(self, text: str, page: int, selected: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setChecked(selected)
        button.clicked.connect(lambda _checked, page_index=page: self._select_page(page_index))
        self._navigation.append(button)
        return button

    def _select_page(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        for index, button in enumerate(self._navigation):
            button.setChecked(index == page)
        if 0 <= page < len(self.PAGE_META):
            eyebrow, title, subtitle = self.PAGE_META[page]
            self.page_eyebrow.setText(eyebrow)
            self.page_title.setText(title)
            self.page_subtitle.setText(subtitle)

    def _build_topbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow, title, subtitle = self.PAGE_META[0]
        self.page_eyebrow = QLabel(eyebrow)
        self.page_eyebrow.setObjectName("eyebrow")
        self.page_title = QLabel(title)
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel(subtitle)
        self.page_subtitle.setObjectName("pageSubtitle")
        heading.addWidget(self.page_eyebrow)
        heading.addWidget(self.page_title)
        heading.addWidget(self.page_subtitle)
        heading.setSpacing(4)
        layout.addLayout(heading)
        layout.addStretch(1)
        self.runtime_state_chip = QLabel("状态 · 等待校准")
        self.runtime_state_chip.setObjectName("runtimeStateChip")
        self.runtime_state_chip.setProperty("state", "idle")
        self.runtime_state_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.runtime_state_chip, 0, Qt.AlignmentFlag.AlignTop)
        self.theme_button = QPushButton()
        self.theme_button.setToolTip("切换日间 / 夜间界面")
        layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignTop)
        self.status_chip = QLabel("●  待校准")
        self.status_chip.setObjectName("statusChip")
        self.status_chip.setProperty("state", "idle")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for control in (
            self.runtime_state_chip,
            self.theme_button,
            self.status_chip,
        ):
            control.setMinimumWidth(96)
            control.setMaximumWidth(136)
            control.setFixedHeight(38)
            control.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
        layout.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignTop)
        return layout

    @staticmethod
    def _spin_box(minimum: int, maximum: int, value: int, suffix: str) -> QSpinBox:
        spin = ScrollSafeSpinBox()
        # 固定使用西文数字，避免部分 Windows 区域设置把数值渲染成异常字形。
        spin.setLocale(QLocale.c())
        spin.setGroupSeparatorShown(False)
        font = QFont("Segoe UI", 10)
        spin.setFont(font)
        if spin.lineEdit() is not None:
            spin.lineEdit().setFont(font)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    @staticmethod
    def _double_spin_box(
        minimum: float,
        maximum: float,
        value: float,
        suffix: str,
    ) -> QDoubleSpinBox:
        spin = ScrollSafeDoubleSpinBox()
        spin.setLocale(QLocale.c())
        spin.setGroupSeparatorShown(False)
        spin.setDecimals(1)
        spin.setSingleStep(0.1)
        font = QFont("Segoe UI", 10)
        spin.setFont(font)
        if spin.lineEdit() is not None:
            spin.lineEdit().setFont(font)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def begin_startup_services(self) -> None:
        """启动页结束后读取一次硬件；按用户设置决定是否检查 Release。"""
        threading.Thread(
            target=self._collect_system_profile_async,
            name="system-profile",
            daemon=True,
        ).start()
        if self.engine.config().github_auto_check:
            self._check_for_updates(manual=False)

    def _collect_system_profile_async(self) -> None:
        try:
            self.profile_ready.emit(collect_system_profile())
        except Exception as error:  # pragma: no cover - 取决于本机 WMI 状态
            from . import record_error as report_error

            report_error("collect system profile", error)
            self.profile_ready.emit(None)

    def _show_system_profile(self, profile: object) -> None:
        if not isinstance(profile, SystemProfile):
            self.cpu_model_label.setText("读取失败，已写入本地错误日志。")
            self.gpu_model_label.setText("读取失败，已写入本地错误日志。")
            self.memory_model_label.setText("读取失败，已写入本地错误日志。")
            return
        set_system_profile(profile)
        self.cpu_model_label.setText(profile.cpu)
        self.gpu_model_label.setText(profile.gpu)
        self.memory_model_label.setText(profile.memory)
        self._append_log("已读取一次本机硬件信息（不持续监测）。", EventKind.INFO)

    def _refresh_calibration_summary(self) -> None:
        config = self.engine.config()
        self._sync_floating_calibration_state()
        if config.capture_mode == "window":
            if config.target_button_offset is None:
                self.calibration_summary.setText("后台模式尚未校准。选择洛奇 M 窗口后，将鼠标放在按钮中心并校准。")
                self._set_runtime_state("等待校准")
                return
            offset_x, offset_y = config.target_button_offset
            self.calibration_summary.setText(
                f"已校准后台目标：{config.target_window_title or '未命名窗口'}  ·  窗口内 ({offset_x}, {offset_y})"
            )
        else:
            if config.button_center is None:
                self.calibration_summary.setText("尚未校准。请把鼠标停在圆形按钮中心后按 F7；记录时鼠标不会移动。")
                self._set_runtime_state("等待校准")
                return
            x, y = config.button_center
            self.calibration_summary.setText(
                f"已校准：({x}, {y})  ·  {config.selected_resolution}  ·  {self._mode_name(config.display_mode)}"
            )
        if not self.engine.is_monitoring():
            self._set_status("idle", "●  已校准，待启动")
            self._set_runtime_state("等待启动")
    def _refresh_threshold_display(self, threshold: int) -> None:
        self.threshold_value.setText(f"{threshold} px")
        if self.recognition_backend_combo.currentData() == "pixel":
            self.red_progress.setMaximum(max(1, threshold))

    def _consume_engine_event(self, event: EngineEvent) -> None:
        if event.kind == EventKind.DIAGNOSTIC:
            saving = event.snapshot_state == "saving"
            self.snapshot_button.setEnabled(not saving)
            self.snapshot_button.setText("正在保存…" if saving else "保存识别现场（F9）")
            if saving:
                self.view_snapshot_button.setEnabled(False)
                self.snapshot_status.setText("正在保存识别现场…F8 / Esc 仍可使用。")
            else:
                self._last_snapshot_path = event.debug_image
                self._last_snapshot_bundle = event.diagnostic_path
                self.view_snapshot_button.setEnabled(event.debug_image is not None)
                self.snapshot_status.setText(
                    "截图和诊断包已保存，仅保存在本机。"
                    if event.snapshot_state == "saved" else event.message
                )
            self.snapshot_status.setToolTip(event.message)
            self._append_log(
                event.message,
                EventKind.WARNING if event.snapshot_state in {"failed", "partial"} else EventKind.INFO,
            )
            return
        # Qt 信号可能晚于 F8 暂停到达，不让旧指标把状态栏改回“运行中”。
        if event.kind == EventKind.METRIC and not self.engine.is_monitoring():
            return
        if event.kind == EventKind.STATE and event.monitoring != self.engine.is_monitoring():
            return
        voice_cue = cue_for_engine_event(
            event.kind,
            event.message,
            event.monitoring,
        )
        if voice_cue == F8_STOP_CUE:
            self.voice_player.clear_pending()
        if voice_cue is not None:
            self.voice_player.play(voice_cue)

        if event.kind == EventKind.METRIC:
            if event.recognition_source in {"ok_feature", "v2_signature", "compass_pixel"}:
                confidence = max(0.0, min(1.0, event.recognition_confidence))
                caption = (
                    "指南针中心黑点"
                    if event.recognition_source == "compass_pixel"
                    else "OK 特征相似度"
                )
                self.red_metric.caption_label.setText(caption)
                self.red_metric.value_label.setText(f"{confidence * 100:.1f}%")
                self.red_progress.setMaximum(1000)
                self.red_progress.setValue(round(confidence * 1000))
            else:
                self.red_metric.caption_label.setText("当前红色像素")
                self.red_metric.value_label.setText(f"{event.red_pixels} px")
                maximum = max(1, self.engine.config().fish_red_pixel_threshold)
                self.red_progress.setMaximum(maximum)
                self.red_progress.setValue(min(event.red_pixels, maximum))
            if event.waiting_for_bounce:
                if event.catch_strategy == "fixed_delay":
                    _wait, _latest, collect_after = FishingEngine.fixed_delay_timing(
                        self.engine.config()
                    )
                    total = max(0.1, collect_after)
                    percent = min(
                        100,
                        round(event.hook_elapsed_seconds / total * 100),
                    )
                    self.stamina_metric.value_label.setText(
                        f"{event.hook_elapsed_seconds:.1f} / {total:.1f} 秒"
                    )
                    self.stamina_progress.setValue(percent)
                elif event.stamina_peak_width:
                    percent = min(100, round(event.stamina_fill_width / event.stamina_peak_width * 100))
                    self.stamina_metric.value_label.setText(f"{percent}% · {event.stamina_fill_width} px")
                    self.stamina_progress.setValue(percent)
                else:
                    self.stamina_metric.value_label.setText("扫描中")
                    self.stamina_progress.setValue(0)
            else:
                self.stamina_metric.value_label.setText("等待上钩")
                self.stamina_progress.setValue(0)
            self.runtime_detail.setText(event.message)
            if event.waiting_for_bounce:
                bounce_states = {
                    "fixed_delay": "定时收鱼",
                    "stamina_bounce": "观察体力条",
                    "instant": "准备收杆",
                }
                self._set_runtime_state(
                    bounce_states.get(event.catch_strategy, "准备收杆"),
                    "running",
                )
            else:
                icon_states = {
                    IconState.NORMAL: "识别中",
                    IconState.READY_TO_CAST: "准备抛竿",
                    IconState.WAITING_BITE: "等待上钩",
                    IconState.FISH_HOOKED: "已经上钩",
                    IconState.IDLE_RECOVERY: "恢复钓鱼",
                    IconState.HORSE_MOUNT_PROMPT: "骑乘纠错",
                    IconState.HORSE_DISMOUNT_PROMPT: "骑乘纠错",
                }
                self._set_runtime_state(
                    icon_states.get(event.icon_state, "识别中"),
                    "running",
                )
            return

        self._sync_learned_escape_status()
        self._append_log(event.message, event.kind)
        if event.kind == EventKind.STATE:
            if event.monitoring:
                self.runtime_title.setText("监测中")
                cleaning_inventory = event.message.startswith(
                    ("自动清理背包", "背包清理调试")
                )
                self.runtime_detail.setText(
                    event.message
                    if cleaning_inventory
                    else (
                        "正在识别指定窗口区域（推荐后台模式）。"
                        if self.engine.config().capture_mode == "window"
                        else "正在识别右下角圆形按钮。"
                    )
                )
                self.start_button.setText("暂停监测")
                self.start_button.setObjectName("dangerButton")
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
                self._set_status("running", "●  监测运行中")
                self._set_runtime_state(
                    "清理背包" if cleaning_inventory else "识别中",
                    "running",
                )
            else:
                self.runtime_title.setText("已暂停")
                self.runtime_detail.setText("暂停期间不会发送按键。")
                self.start_button.setText("开始监测")
                self.start_button.setObjectName("primaryButton")
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
                self._refresh_calibration_summary()
                self._set_runtime_state("已暂停")
        elif event.kind == EventKind.WARNING:
            self._set_status("warning", "●  需要注意")
            self._set_runtime_state("需要处理", "warning")
            self.runtime_detail.setText(event.message)
        elif event.kind == EventKind.ERROR:
            if self.engine.is_monitoring():
                # 保存快照等辅助操作报错不等于钓鱼线程已经停止。
                self._set_status("warning", "●  运行中 · 需要注意")
                self.runtime_detail.setText(event.message)
                return
            self._set_status("warning", "●  识别已暂停")
            self._set_runtime_state("已停止", "warning")
            self.runtime_detail.setText(event.message)
            self.runtime_title.setText("已暂停")
            self.start_button.setText("开始监测")
            self.start_button.setObjectName("primaryButton")
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
        elif event.kind == EventKind.SUCCESS:
            self.runtime_detail.setText(event.message)
            if event.debug_image is not None:
                self.snapshot_status.setText("区域快照与识别诊断已保存")
            self._refresh_calibration_summary()
        if hasattr(self, "test_inventory_cleanup_button"):
            self._sync_inventory_cleanup_debug_controls()

    def _set_runtime_state(self, text: str, state: str = "idle") -> None:
        self.runtime_state_chip.setProperty("state", state)
        self.runtime_state_chip.setText(f"状态 · {text}")
        self.runtime_state_chip.style().unpolish(self.runtime_state_chip)
        self.runtime_state_chip.style().polish(self.runtime_state_chip)
        self.floating_status_bar.set_runtime(text, state)

    def _set_status(self, state: str, text: str) -> None:
        self.status_chip.setProperty("state", state)
        self.status_chip.setText(text)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

    def _append_log(self, message: str, kind: EventKind) -> None:
        labels = {
            EventKind.INFO: "信息",
            EventKind.SUCCESS: "完成",
            EventKind.WARNING: "提醒",
            EventKind.ERROR: "错误",
            EventKind.STATE: "状态",
            EventKind.CONFIG: "配置",
        }
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {labels.get(kind, '事件')}  {message}")

    @staticmethod
    def _select_combo_data(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    @staticmethod
    def _select_combo_text(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index < 0:
            combo.addItem(value)
            index = combo.count() - 1
        combo.setCurrentIndex(index)

    @staticmethod
    def _mode_name(value: str) -> str:
        return {"borderless": "无边框全屏", "fullscreen": "独占全屏", "windowed": "窗口模式"}.get(value, value)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.WindowStateChange
            and hasattr(self, "floating_status_bar")
        ):
            old_state = event.oldState()  # type: ignore[attr-defined]
            was_minimized = bool(
                old_state & Qt.WindowState.WindowMinimized
            )
            is_minimized = self.isMinimized()
            if hasattr(self, "voice_player"):
                if is_minimized and not was_minimized:
                    self.voice_player.play(WINDOW_MINIMIZED_CUE)
                elif was_minimized and not is_minimized:
                    self.voice_player.play(WINDOW_RESTORED_CUE)
            self._sync_floating_status_visibility()

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        self.floating_status_bar.close()
        self.voice_player.close()
        self.engine.close()
        event.accept()  # type: ignore[union-attr]
