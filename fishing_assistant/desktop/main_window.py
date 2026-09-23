"""主窗口组装、Qt 信号及窗口生命周期；页面布局和交互按职责分文件。"""
from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from fishing_assistant import window_target
from fishing_assistant.constants import APP_AUTHOR, APP_ICON_PATH, APP_NAME, APP_VERSION
from fishing_assistant.desktop.controllers.configuration import ConfigurationControllerMixin
from fishing_assistant.desktop.controllers.events import EngineEventsMixin
from fishing_assistant.desktop.controllers.fishing import FishingSettingsControllerMixin
from fishing_assistant.desktop.controllers.floating_controls import FloatingControlsMixin
from fishing_assistant.desktop.controllers.preferences import PreferencesControllerMixin
from fishing_assistant.desktop.controllers.services import ApplicationServicesMixin
from fishing_assistant.desktop.dialogs import UpdateAvailableDialog
from fishing_assistant.desktop.floating_status import FloatingStatusBar
from fishing_assistant.desktop.forms import FormHelpersMixin
from fishing_assistant.desktop.pages.dashboard import DashboardPageMixin
from fishing_assistant.desktop.pages.crafting import CraftingHubPage
from fishing_assistant.desktop.pages.fishing import FishingPageMixin
from fishing_assistant.desktop.pages.help import HelpPageMixin
from fishing_assistant.desktop.pages.settings import SettingsPageMixin
from fishing_assistant.desktop.pages.thresholds import ThresholdPageMixin
from fishing_assistant.desktop.styles import DAY_STYLE, NIGHT_STYLE
from fishing_assistant.engine import EventKind, FishingEngine
from fishing_assistant.voice_alerts import (
    VoiceAlertPlayer,
    WINDOW_MINIMIZED_CUE,
    WINDOW_RESTORED_CUE,
)
from pathlib import Path


class MainWindow(
    FloatingControlsMixin,
    DashboardPageMixin,
    FishingPageMixin,
    ThresholdPageMixin,
    SettingsPageMixin,
    HelpPageMixin,
    FormHelpersMixin,
    ConfigurationControllerMixin,
    FishingSettingsControllerMixin,
    PreferencesControllerMixin,
    ApplicationServicesMixin,
    EngineEventsMixin,
    QMainWindow,
):
    """配置中心、运行状态与操作日志组成的单窗口桌面应用。"""

    PAGE_META = (
        ("LOCAL AUTOMATION · OVERVIEW", "钓鱼控制台", "校准、启动和运行状态集中在这里。"),
        ("FISHING · BEHAVIOR", "钓鱼设置", "设置收鱼方式、自动续钓和指南针恢复。"),
        ("CRAFTING · QUEUE", "自动制作（测试）", "选择加工材料，自动补充队列并领取产物。"),
        ("DETECTION · TUNING", "识别阈值", "调整图标识别方式、区域和兼容模式阈值。"),
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
        self._floating_crafting_session = False
        self.floating_status_bar = FloatingStatusBar()
        self.floating_status_bar.pause_requested.connect(self._pause_from_floating)
        self.floating_status_bar.resume_requested.connect(self._resume_from_floating)

        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setMinimumSize(920, 680)
        self.resize(980, 760)
        # 页面构建时就会 polish 控件。先用保存的主题，避免首帧缓存夜间颜色。
        self.setStyleSheet(DAY_STYLE if self.engine.config().ui_theme == "day" else NIGHT_STYLE)

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
        from fishing_assistant.features.crafting.page import CraftingPage
        self.crafting_page = CraftingPage(self.engine)
        self.crafting_hub = CraftingHubPage(self.crafting_page)
        self.stack.addWidget(self.crafting_hub)
        self.stack.addWidget(self._build_threshold_page())
        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_help_page())
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(184)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(5)

        brand_row = QHBoxLayout()
        mark = QLabel()
        mark.setObjectName("brandMark")
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setFixedSize(36, 36)
        icon = QPixmap(str(APP_ICON_PATH))
        if not icon.isNull():
            mark.setPixmap(
                icon.scaled(
                    36,
                    36,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        brand_text = QVBoxLayout()
        title = QLabel("洛奇 M 钓鱼助手")
        title.setObjectName("brandTitle")
        subtitle = QLabel("钓鱼 · 制作")
        subtitle.setObjectName("brandSubtitle")
        brand_text.addWidget(title)
        brand_text.addWidget(subtitle)
        brand_text.setSpacing(1)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_text, 1)
        layout.addLayout(brand_row)
        layout.addSpacing(22)
        workspace_label = QLabel("工作台")
        workspace_label.setObjectName("navSection")
        layout.addWidget(workspace_label)

        layout.addWidget(self._nav_button("控制台", 0, True))
        layout.addWidget(self._nav_button("钓鱼设置", 1))
        layout.addWidget(self._nav_button("自动制作（测试）", 2))
        layout.addWidget(self._nav_button("识别阈值", 3))
        layout.addStretch(1)
        application_label = QLabel("应用")
        application_label.setObjectName("navSection")
        layout.addWidget(application_label)
        layout.addWidget(self._nav_button("设置", 4))
        layout.addWidget(self._nav_button("使用说明", 5))
        layout.addSpacing(14)

        footer = QLabel(f"v{APP_VERSION}  ·  {APP_AUTHOR}")
        footer.setObjectName("brandSubtitle")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)
        return sidebar

    def _nav_button(self, text: str, page: int, selected: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("navButton")
        button.setCheckable(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setMinimumHeight(38)
        button.setChecked(selected)
        button.clicked.connect(lambda _checked, page_index=page: self._select_page(page_index))
        self._navigation.append(button)
        return button

    def _select_page(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        for index, button in enumerate(self._navigation):
            button.setChecked(index == page)
        if 0 <= page < len(self.PAGE_META):
            _eyebrow, title, subtitle = self.PAGE_META[page]
            self.page_title.setText(title)
            self.page_title.setToolTip(subtitle)

    def _build_topbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        heading = QVBoxLayout()
        _eyebrow, title, subtitle = self.PAGE_META[0]
        self.page_title = QLabel(title)
        self.page_title.setObjectName("pageTitle")
        self.page_title.setToolTip(subtitle)
        heading.addWidget(self.page_title)
        heading.setSpacing(4)
        layout.addLayout(heading)
        layout.addStretch(1)
        self.runtime_state_chip = QLabel("状态 · 等待校准")
        self.runtime_state_chip.setObjectName("runtimeStateChip")
        self.runtime_state_chip.setProperty("state", "idle")
        self.runtime_state_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.runtime_state_chip, 0, Qt.AlignmentFlag.AlignTop)
        self.floating_status_button = QPushButton()
        self.floating_status_button.setObjectName("floatingStatusButton")
        self.floating_status_button.setCheckable(True)
        self.floating_status_button.setToolTip("切换最小化后的悬浮状态栏")
        layout.addWidget(self.floating_status_button, 0, Qt.AlignmentFlag.AlignTop)
        self.theme_button = QPushButton()
        self.theme_button.setToolTip("切换日间 / 夜间界面")
        layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignTop)
        self.status_chip = QLabel("●  待校准")
        self.status_chip.setObjectName("statusChip")
        self.status_chip.setProperty("state", "idle")
        self.status_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for control in (
            self.runtime_state_chip,
            self.floating_status_button,
            self.theme_button,
            self.status_chip,
        ):
            control.setFixedSize(136, 38)
        layout.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignTop)
        return layout

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
        if hasattr(self, "remote_panel"):
            self.remote_panel.shutdown()
        self.floating_status_bar.close()
        self.voice_player.close()
        self.engine.close()
        event.accept()  # type: ignore[union-attr]
