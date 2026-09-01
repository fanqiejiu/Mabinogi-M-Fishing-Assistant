"""Qt 桌面界面。所有业务操作由 FishingEngine 完成，UI 只负责呈现和配置。"""

from __future__ import annotations

import threading
from datetime import datetime

import mss
from PySide6.QtCore import QLocale, QSignalBlocker, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,

    QMainWindow,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from . import window_target
from .config import (
    AppConfig,
    default_config,
    effective_roi_size,
    parse_resolution,
    resolution_label_for_size,
)
from .constants import (
    APP_AUTHOR,
    APP_DISPLAY_VERSION,
    APP_ICON_PATH,
    APP_NAME,
    APP_VERSION,
    GITHUB_REPOSITORY,
)
from .diagnostics import (
    LOG_DIR,
    VISION_DIAGNOSTICS_DIR,
    create_support_bundle,
    record_error,
    set_system_profile,
)
from .engine import EngineEvent, EventKind, FishingEngine, IconState
from .system_profile import SystemProfile, collect_system_profile
from .updates import UpdateResult, check_github_release


NIGHT_STYLE = """
QMainWindow { background: #09111F; color: #F7FAFC; }
QDialog#updateDialog { background: #111D2F; }
QWidget { color: #EEF4FB; font-family: 'Segoe UI'; }
QFrame#sidebar { background: #0D1728; border-right: 1px solid #1E2B3E; }
QFrame#contentSurface { background: #09111F; }
QFrame#card, QFrame#metricCard {
    background: #111D2F;
    border: 1px solid #22324A;
    border-radius: 16px;
}
QFrame#metricCard { border-radius: 12px; background: #0D192A; }
QFrame#backendOptions, QFrame#strategyOption {
    background: #0D192A; border: 1px solid #263A54; border-radius: 10px;
}
QFrame#backendOptions[modeActive="true"] { background: #102A31; border-color: #2DB88B; }
QFrame#backendOptions[modeActive="true"] QLabel#formLabel { color: #E8FFF7; }
QFrame#backendOptions[modeActive="true"] QLabel#helper { color: #94C9B8; }
QLabel#backendModeBadge { color: #75E4BE; font-size: 11px; font-weight: 700; }
QFrame#backendOptions:disabled { background: #0A1423; border-color: #1C2A3D; }
QFrame#backendOptions:disabled QLabel { color: #5E728A; }
QFrame#backendOptions:disabled QComboBox, QFrame#backendOptions:disabled QPushButton {
    background: #0A1423; border-color: #203047; color: #5E728A;
}
QLabel#eyebrow { color: #7F9BBC; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#pageTitle { color: #F8FBFF; font-size: 25px; font-weight: 700; }
QLabel#pageSubtitle { color: #91A5BF; font-size: 13px; }
QLabel#cardTitle { color: #F7FAFC; font-size: 16px; font-weight: 700; }
QLabel#cardHint, QLabel#helper { color: #8296B0; font-size: 12px; }
QLabel#metricValue { color: #F9FCFF; font-size: 24px; font-weight: 700; }
QLabel#metricCaption { color: #8296B0; font-size: 11px; }
QLabel#formLabel { color: #DDE8F5; font-size: 12px; font-weight: 700; }
QLabel#helpStep { color: #C6D6E7; padding: 7px 0; font-size: 13px; }
QLabel#brandMark {
    background: transparent; border: 0;
}
QLabel#brandTitle { color: #F7FAFC; font-size: 15px; font-weight: 700; }
QLabel#brandSubtitle { color: #6F86A5; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; }
QLabel#statusChip {
    background: #1B293C; border: 1px solid #2B3D56; border-radius: 14px;
    color: #AABCD2; padding: 6px 11px; font-size: 12px; font-weight: 700;
}
QLabel#statusChip[state="running"] { background: #123629; border-color: #1F7556; color: #80E7BF; }
QLabel#statusChip[state="warning"] { background: #3A2C14; border-color: #82631F; color: #F6CF6A; }
QLabel#runtimeStateChip {
    background: #0D192A; border: 1px solid #29415E; border-radius: 10px;
    color: #AFC3DA; padding: 9px 12px; font-size: 12px; font-weight: 700;
}
QLabel#runtimeStateChip[state="running"] { background: #102A31; border-color: #2DB88B; color: #75E4BE; }
QLabel#runtimeStateChip[state="warning"] { background: #3A2C14; border-color: #82631F; color: #F6CF6A; }
QFrame#timingCallout { background: #0A1626; border: 1px solid #29415E; border-radius: 9px; }
QLabel#timingTitle { color: #75E4BE; font-size: 13px; font-weight: 800; }
QLabel#updateDialogTitle { color: #F8FBFF; font-size: 19px; font-weight: 800; }
QLabel#updateDialogVersion { color: #75E4BE; font-size: 14px; font-weight: 700; }
QTextBrowser#releaseNotes {
    background: #0A1626; border: 1px solid #29415E; border-radius: 9px;
    color: #C8D6E6; padding: 9px; font-family: 'Segoe UI'; font-size: 12px;
}
QPushButton#navButton {
    border: 0; border-radius: 10px; color: #8EA2BD; text-align: left;
    padding: 11px 14px; font-size: 13px; font-weight: 600;
}
QPushButton#navButton:hover { background: #16263B; color: #EDF6FF; }
QPushButton#navButton:checked { background: #173A37; color: #77E4BE; }
QPushButton { border: 1px solid #30455F; background: #17263A; border-radius: 10px; padding: 10px 15px; color: #DCE8F4; font-weight: 700; }
QPushButton:hover { background: #21354E; border-color: #45627F; }
QPushButton:pressed { background: #132033; }
QPushButton#primaryButton { background: #1CB984; color: #06130F; border: 1px solid #42D4A4; }
QPushButton#primaryButton:hover { background: #39D3A1; border-color: #7DEAC6; }
QPushButton#dangerButton { background: #3B2930; border-color: #6B3E4D; color: #FDB5BF; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #0B1626; border: 1px solid #2B405B; border-radius: 9px;
    padding: 9px 11px; min-height: 20px; color: #EDF5FE;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: #4B6E94; }
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { background: #0A1423; border-color: #203047; color: #5E728A; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: #132136; border: 1px solid #314963; selection-background-color: #1C5448; color: #EEF5FD; }
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 19px; border: 0;
}
QCheckBox { color: #DCE8F4; font-weight: 600; spacing: 9px; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #3B526E; border-radius: 5px; background: #0B1626; }
QCheckBox::indicator:checked { background: #1CB984; border-color: #42D4A4; }
QSlider::groove:horizontal { height: 6px; background: #203149; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #21BC8A; border-radius: 3px; }
QSlider::handle:horizontal { background: #C7FFE9; width: 16px; margin: -5px 0; border-radius: 8px; }
QProgressBar { background: #0A1525; border: 0; border-radius: 5px; min-height: 9px; text-align: center; }
QProgressBar::chunk { background: #21BC8A; border-radius: 5px; }
QPlainTextEdit { background: #0A1423; border: 1px solid #233650; border-radius: 10px; padding: 10px; color: #AFC4DC; font-family: 'Cascadia Mono'; font-size: 11px; }
QScrollArea, QWidget#pageCanvas { border: 0; background: #09111F; }
QScrollBar:vertical { background: #0C1727; width: 11px; margin: 4px 2px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #3A526F; border-radius: 4px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: #567394; }
QScrollBar::handle:vertical:pressed { background: #6B8BAD; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


DAY_STYLE = NIGHT_STYLE + """
QMainWindow, QFrame#contentSurface, QScrollArea, QWidget#pageCanvas { background: #F4F7FB; color: #172236; }
QDialog#updateDialog { background: #FFFFFF; }
QWidget { color: #1B2A40; }
QFrame#sidebar { background: #FFFFFF; border-right-color: #D9E3EF; }
QFrame#card, QFrame#metricCard { background: #FFFFFF; border-color: #D7E2EE; }
QFrame#metricCard { background: #F8FBFE; }
QFrame#backendOptions, QFrame#strategyOption { background: #F8FBFE; border-color: #D4E0EC; }
QFrame#backendOptions[modeActive="true"] { background: #ECFAF5; border-color: #70CBAE; }
QFrame#backendOptions[modeActive="true"] QLabel#formLabel { color: #163F34; }
QFrame#backendOptions[modeActive="true"] QLabel#helper { color: #47776A; }
QLabel#backendModeBadge { color: #16835F; }
QFrame#backendOptions:disabled { background: #EEF3F8; border-color: #D9E3ED; }
QFrame#backendOptions:disabled QLabel { color: #8A9AAF; }
QFrame#backendOptions:disabled QComboBox, QFrame#backendOptions:disabled QPushButton {
    background: #EEF3F8; border-color: #D9E3ED; color: #8A9AAF;
}
QLabel#eyebrow, QLabel#brandSubtitle, QLabel#metricCaption, QLabel#cardHint, QLabel#helper, QLabel#pageSubtitle { color: #667B95; }
QLabel#pageTitle, QLabel#cardTitle, QLabel#metricValue, QLabel#brandTitle { color: #14233A; }
QLabel#statusChip { background: #EDF2F7; border-color: #D3DFEC; color: #556B85; }
QLabel#statusChip[state="running"] { background: #E0F7EE; border-color: #8DDBC0; color: #187352; }
QLabel#statusChip[state="warning"] { background: #FFF5D8; border-color: #EDD38B; color: #86620B; }
QLabel#runtimeStateChip { background: #F4F8FC; border-color: #C9D8E8; color: #536B85; }
QLabel#runtimeStateChip[state="running"] { background: #E0F7EE; border-color: #8DDBC0; color: #187352; }
QLabel#runtimeStateChip[state="warning"] { background: #FFF5D8; border-color: #EDD38B; color: #86620B; }
QFrame#timingCallout { background: #F4F9FC; border-color: #C9D8E8; }
QLabel#timingTitle { color: #16835F; }
QLabel#updateDialogTitle { color: #14233A; }
QLabel#updateDialogVersion { color: #16835F; }
QTextBrowser#releaseNotes { background: #F7FAFD; border-color: #C9D8E8; color: #304A66; }
QPushButton#navButton { color: #60758E; }
QPushButton#navButton:hover { background: #EDF3F8; color: #172C48; }
QPushButton#navButton:checked { background: #DDF5EA; color: #107450; }
QPushButton { background: #F5F8FC; border-color: #C9D8E8; color: #26415F; }
QPushButton:hover { background: #EAF1F8; border-color: #9CB6D1; }
QPushButton:pressed { background: #DCE8F3; }
QPushButton#dangerButton { background: #FFF0F2; border-color: #E6A3AE; color: #9A3442; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #FFFFFF; border-color: #C8D7E6; color: #1C304A; }
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover { border-color: #81A4C9; }
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { background: #EEF3F8; border-color: #D9E3ED; color: #8A9AAF; }
QComboBox QAbstractItemView { background: #FFFFFF; border-color: #C8D7E6; selection-background-color: #DDF5EA; color: #1C304A; }
QSlider::groove:horizontal { background: #D7E3EF; }
QSlider::handle:horizontal { background: #158D68; }
QPlainTextEdit { background: #F8FBFE; border-color: #D4E0EC; color: #425C79; }
QScrollBar:vertical { background: #E4ECF4; }
QScrollBar::handle:vertical { background: #A7BDCF; }
QScrollBar::handle:vertical:hover { background: #819EB8; }
QScrollBar::handle:vertical:pressed { background: #6688A6; }
QProgressBar { background: #DCE8F3; }
QProgressBar::chunk { background: #20A977; }
QCheckBox { color: #29415D; }
QLabel#formLabel { color: #263B55; }
QLabel#helpStep { color: #3D5774; }
"""


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")


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


class UpdateAvailableDialog(QDialog):
    """不遮挡主界面的紧凑更新提醒。"""

    def __init__(self, result: UpdateResult, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._release_url = result.release_url
        self.setObjectName("updateDialog")
        self.setWindowTitle("发现新版本")
        self.setModal(False)
        self.setMinimumWidth(380)
        self.setMaximumWidth(430)
        self.setMaximumHeight(520)
        self.setSizeGripEnabled(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)

        title = QLabel("发现新版本")
        title.setObjectName("updateDialogTitle")
        layout.addWidget(title)
        latest = result.latest_version or "新版本"
        version = QLabel(f"当前 v{APP_VERSION}  →  {latest}")
        version.setObjectName("updateDialogVersion")
        layout.addWidget(version)
        message = QLabel("新版本已经发布，可以前往 GitHub 查看更新内容并下载。")
        message.setObjectName("cardHint")
        message.setWordWrap(True)
        layout.addWidget(message)

        notes_title = QLabel("Release 更新说明")
        notes_title.setObjectName("formLabel")
        layout.addWidget(notes_title)
        self.release_notes = QTextBrowser()
        self.release_notes.setObjectName("releaseNotes")
        self.release_notes.setOpenExternalLinks(True)
        self.release_notes.setMinimumHeight(105)
        self.release_notes.setMaximumHeight(180)
        self.release_notes.setMarkdown(
            result.release_notes or "本次 Release 未填写更新说明。"
        )
        layout.addWidget(self.release_notes)

        actions = QHBoxLayout()
        actions.addStretch(1)
        later_button = QPushButton("关闭")
        later_button.clicked.connect(self.close)
        actions.addWidget(later_button)
        release_button = QPushButton("前往更新")
        release_button.setObjectName("primaryButton")
        release_button.setEnabled(bool(self._release_url))
        release_button.clicked.connect(self._open_release)
        actions.addWidget(release_button)
        layout.addLayout(actions)

    def _open_release(self) -> None:
        if self._release_url:
            QDesktopServices.openUrl(QUrl(self._release_url))
        self.close()


class MainWindow(QMainWindow):
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
        self.engine.set_event_callback(self.engine_event.emit)
        self.engine_event.connect(self._consume_engine_event)
        self.profile_ready.connect(self._show_system_profile)
        self.update_ready.connect(self._show_update_result)
        self._navigation: list[QPushButton] = []
        self._last_release_url: str | None = None
        self._notified_release_version: str | None = None
        self._update_dialog: UpdateAvailableDialog | None = None
        self._auto_detected_game_window: window_target.WindowInfo | None = None

        self.setWindowTitle(APP_NAME)
        if APP_ICON_PATH.exists():
            self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        self.setMinimumSize(920, 680)
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
        self.runtime_state_chip.setMinimumWidth(132)
        self.runtime_state_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.runtime_state_chip, 0, Qt.AlignmentFlag.AlignTop)
        self.theme_button = QPushButton()
        self.theme_button.setToolTip("切换日间 / 夜间界面")
        layout.addWidget(self.theme_button, 0, Qt.AlignmentFlag.AlignTop)
        self.status_chip = QLabel("●  待校准")
        self.status_chip.setObjectName("statusChip")
        self.status_chip.setProperty("state", "idle")
        layout.addWidget(self.status_chip, 0, Qt.AlignmentFlag.AlignTop)
        return layout

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
        layout.setSpacing(16)

        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_runtime_card())
        layout.addWidget(self._build_log_card(), 1)

        scroll.setWidget(canvas)
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
        form.addWidget(self._form_label("操作按键", "上钩时发送至前台游戏"), 2, 1)
        key_value = QLabel("Space")
        key_value.setObjectName("metricValue")
        key_value.setStyleSheet("font-size: 20px; padding: 8px 0;")
        form.addWidget(key_value, 3, 1)
        layout.addLayout(form)

        target = QGridLayout()
        target.setHorizontalSpacing(18)
        target.setVerticalSpacing(10)
        self.target_mode_combo = ScrollSafeComboBox()
        self.target_mode_combo.addItem("屏幕坐标模式（稳定）", "screen")
        self.target_mode_combo.addItem("指定窗口后台模式（实验性）", "window")
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
                "屏幕模式要求游戏在前台；后台模式只向指定窗口投递按键",
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

        debug_row = QHBoxLayout()
        self.snapshot_status = QLabel("尚未保存区域快照")
        self.snapshot_status.setObjectName("cardHint")
        self.snapshot_button = QPushButton("检查识别区域")
        debug_row.addWidget(self.snapshot_status, 1)
        debug_row.addWidget(self.snapshot_button)
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

    def _build_detection_page(self) -> QScrollArea:
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
        layout.setSpacing(16)

        strategy_card = Card()
        strategy_layout = QVBoxLayout(strategy_card)
        strategy_layout.setContentsMargins(22, 20, 22, 22)
        strategy_layout.setSpacing(16)
        strategy_layout.addLayout(
            self._card_heading(
                "收鱼策略",
                "选择上钩后的处理方式；每种模式只显示自己需要的参数。",
            )
        )

        catch_grid = QGridLayout()
        catch_grid.setHorizontalSpacing(16)
        catch_grid.setVerticalSpacing(10)
        self.catch_strategy_combo = ScrollSafeComboBox()
        self.catch_strategy_combo.addItem(
            "模式 1：体力条反弹",
            "stamina_bounce",
        )
        self.catch_strategy_combo.addItem(
            "模式 2：定时收鱼（推荐）", "fixed_delay"
        )
        self.catch_strategy_combo.addItem(
            "模式 3：上钩立即收杆", "instant"
        )
        self.fallback_delay_spin = self._double_spin_box(
            0.1, 60.0, 5.3, " 秒"
        )
        self.latest_collect_spin = self._double_spin_box(
            0.1, 60.0, 10.5, " 秒"
        )
        self.stamina_zoom_spin = self._spin_box(0, 12, 5, " 格")

        def option_panel(
            title: str, hint: str, control: QWidget | None = None
        ) -> QFrame:
            panel = QFrame()
            panel.setObjectName("strategyOption")
            option_layout = QVBoxLayout(panel)
            option_layout.setContentsMargins(14, 12, 14, 12)
            option_layout.setSpacing(5)
            option_layout.addWidget(self._form_label(title, hint))
            if control is not None:
                option_layout.addWidget(control)
            return panel

        self.learned_escape_label = QLabel()
        self.learned_escape_label.setObjectName("helper")
        self.learned_escape_label.setWordWrap(True)
        mode_one_panel = option_panel(
            "向上滚轮次数",
            "启动模式 1 时会向上滚轮放大游戏画面；0 表示不自动滚动。",
            self.stamina_zoom_spin,
        )
        timing_panel = QFrame()
        timing_panel.setObjectName("timingCallout")
        timing_layout = QVBoxLayout(timing_panel)
        timing_layout.setContentsMargins(12, 10, 12, 10)
        timing_layout.setSpacing(4)
        timing_title = QLabel("钓鱼计时")
        timing_title.setObjectName("timingTitle")
        timing_layout.addWidget(timing_title)
        timing_layout.addWidget(self.learned_escape_label)
        mode_one_panel.layout().addWidget(timing_panel)

        mode_two_panel = QFrame()
        mode_two_panel.setObjectName("strategyOption")
        mode_two_layout = QVBoxLayout(mode_two_panel)
        mode_two_layout.setContentsMargins(14, 12, 14, 12)
        mode_two_layout.setSpacing(10)
        mode_two_layout.addWidget(
            self._form_label(
                "模式二计时",
                "垃圾通常约 5 秒消失，普通鱼约 11 秒消失；两个时间均支持 0.1 秒微调。",
            )
        )
        mode_two_grid = QGridLayout()
        mode_two_grid.setHorizontalSpacing(14)
        mode_two_grid.setVerticalSpacing(6)
        mode_two_grid.addWidget(
            self._form_label("等待收杆秒数", "默认 5.3 秒，用于跳过较早消失的垃圾。"),
            0,
            0,
        )
        mode_two_grid.addWidget(
            self._form_label("最迟空格拉钩秒数", "默认 10.5 秒，在普通鱼消失前留出余量。"),
            0,
            1,
        )
        mode_two_grid.addWidget(self.fallback_delay_spin, 1, 0)
        mode_two_grid.addWidget(self.latest_collect_spin, 1, 1)
        mode_two_grid.setColumnStretch(0, 1)
        mode_two_grid.setColumnStretch(1, 1)
        mode_two_layout.addLayout(mode_two_grid)
        self.fixed_delay_effective_hint = QLabel()
        self.fixed_delay_effective_hint.setObjectName("helper")
        self.fixed_delay_effective_hint.setWordWrap(True)
        mode_two_layout.addWidget(self.fixed_delay_effective_hint)

        self.catch_option_stack = QStackedWidget()
        self.catch_option_stack.addWidget(mode_one_panel)
        self.catch_option_stack.addWidget(mode_two_panel)
        self.catch_option_stack.addWidget(
            option_panel(
                "模式 3 已就绪",
                "检测到上钩图标后立即按 Space 收杆，无额外参数。",
            )
        )
        catch_grid.addWidget(
            self._form_label(
                "收鱼模式",
                "模式 1 会定位体力槽中点，连续确认灰色后等待它恢复绿色。",
            ),
            0,
            0,
        )
        catch_grid.addWidget(self.catch_strategy_combo, 1, 0)
        catch_grid.addWidget(
            self._form_label("当前模式参数", "只显示当前模式需要的设置。"),
            2,
            0,
        )
        catch_grid.addWidget(self.catch_option_stack, 3, 0)
        catch_grid.setColumnStretch(0, 1)
        strategy_layout.addLayout(catch_grid)
        self.catch_strategy_hint = QLabel()
        self.catch_strategy_hint.setObjectName("cardHint")
        self.catch_strategy_hint.setWordWrap(True)
        strategy_layout.addWidget(self.catch_strategy_hint)
        layout.addWidget(strategy_card)

        recovery_card = Card()
        recovery_layout = QVBoxLayout(recovery_card)
        recovery_layout.setContentsMargins(22, 20, 22, 22)
        recovery_layout.setSpacing(14)
        recovery_layout.addLayout(
            self._card_heading(
                "自动恢复与续钓",
                "指南针出现时执行 W → S；钓鱼图标恢复后自动按 Space。",
            )
        )
        self.auto_resume_check = QCheckBox(
            "收鱼后自动按 Space 继续钓鱼"
        )
        self.auto_recover_check = QCheckBox(
            "检测到指南针状态时自动执行 W → S"
        )
        recovery_layout.addWidget(self.auto_resume_check)
        recovery_layout.addWidget(self.auto_recover_check)

        recovery_grid = QGridLayout()
        recovery_grid.setHorizontalSpacing(16)
        recovery_grid.setVerticalSpacing(10)
        self.recovery_hold_spin = self._spin_box(80, 600, 180, " ms")
        self.recovery_cooldown_spin = self._spin_box(
            1000, 10000, 4500, " ms"
        )
        self.recovery_attempt_limit_spin = self._spin_box(1, 20, 5, " 次")
        recovery_controls = [
            (
                "W / S 按住时间",
                "每个方向的短按时长",
                self.recovery_hold_spin,
            ),
            (
                "恢复冷却",
                "避免持续失效时反复移动",
                self.recovery_cooldown_spin,
            ),
            (
                "W/S 恢复上限",
                "连续失败达到上限后停止监测",
                self.recovery_attempt_limit_spin,
            ),
        ]
        for index, (label, hint, control) in enumerate(recovery_controls):
            row = (index // 2) * 2
            column = index % 2
            recovery_grid.addWidget(
                self._form_label(label, hint), row, column
            )
            recovery_grid.addWidget(control, row + 1, column)
            recovery_grid.setColumnStretch(column, 1)
        recovery_layout.addLayout(recovery_grid)
        layout.addWidget(recovery_card)
        layout.addStretch(1)
        scroll.setWidget(canvas)
        return scroll

    def _build_threshold_page(self) -> QScrollArea:
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
        layout.setSpacing(16)

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
        threshold_header = QHBoxLayout()
        self.threshold_header_label = self._form_label(
            "旧像素模式：鱼体判定阈值",
            "仅在旧像素识别下生效；OK 模式使用图片特征相似度。",
        )
        threshold_header.addWidget(self.threshold_header_label, 1)
        threshold_header.addWidget(self.threshold_value)
        recognition_layout.addLayout(threshold_header)
        recognition_layout.addWidget(self.threshold_slider)
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
        scroll.setWidget(canvas)
        return scroll
    def _build_help_page(self) -> QScrollArea:
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
        layout.setSpacing(16)

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 24)
        card_layout.setSpacing(12)
        card_layout.addLayout(self._card_heading("开始前检查", "一次正确校准比固定等待时间更可靠。"))
        steps = [
            "1. 在游戏内确认分辨率和画面模式，然后在“控制台”中选择对应配置。",
            "2. 把鼠标停在右下角圆形钓鱼按钮的正中心，直接按 F7；不会弹出确认，也不会移动鼠标。",
            "3. 用“检查识别区域”保存快照，确认圆形按钮没有被截断。",
            "4. 游戏回到前台后点击“开始监测”或按 F8；Esc 会紧急停止监测。",
        ]
        for step in steps:
            label = QLabel(step)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            card_layout.addWidget(label)
        layout.addWidget(card)

        hotkeys = Card()
        hotkey_layout = QGridLayout(hotkeys)
        hotkey_layout.setContentsMargins(24, 20, 24, 20)
        hotkey_layout.addWidget(QLabel("全局快捷键"), 0, 0, 1, 2)
        hotkey_layout.itemAtPosition(0, 0).widget().setObjectName("cardTitle")
        for row, (key, description) in enumerate(
            (("F7", "立即记录当前鼠标位置为钓鱼按钮中心（不移动鼠标）"), ("F8", "开始或暂停监测"), ("F9", "保存识别区域与完整诊断包"), ("Esc", "紧急停止监测")),
            start=1,
        ):
            key_label = QLabel(key)
            key_label.setObjectName("metricValue")
            key_label.setStyleSheet("font-size: 18px;")
            detail = QLabel(description)
            detail.setObjectName("cardHint")
            hotkey_layout.addWidget(key_label, row, 0)
            hotkey_layout.addWidget(detail, row, 1)
        layout.addWidget(hotkeys)
        layout.addStretch(1)
        scroll.setWidget(canvas)
        return scroll

    def _build_settings_page(self) -> QScrollArea:
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
        layout.setSpacing(16)

        identity = Card()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(24, 22, 24, 22)
        identity_layout.setSpacing(7)
        identity_layout.addLayout(self._card_heading("应用设置"))
        version = QLabel(f"{APP_NAME}  ·  v{APP_VERSION}")
        version.setObjectName("metricValue")
        version.setStyleSheet("font-size: 18px; padding-top: 5px;")
        identity_layout.addWidget(version)
        ok_credit = QLabel(
            '后台自动化核心：<a href="https://github.com/ok-oldking/ok-script">ok-script</a> '
            '（Apache-2.0 + Commons Clause）。'
        )
        ok_credit.setObjectName("cardHint")
        ok_credit.setOpenExternalLinks(True)
        ok_credit.setWordWrap(True)
        identity_layout.addWidget(ok_credit)
        layout.addWidget(identity)
        layout.addWidget(self._build_hardware_card())

        update_card = Card()
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(24, 22, 24, 24)
        update_layout.setSpacing(14)
        update_layout.addLayout(
            self._card_heading(
                "GitHub 更新检查",
                "更新源固定为本项目仓库；可选择是否在启动时自动检查。",
            )
        )
        update_grid = QGridLayout()
        update_grid.setHorizontalSpacing(18)
        update_grid.setVerticalSpacing(7)
        update_grid.addWidget(self._form_label("GitHub 仓库", "更新源固定为当前项目"), 0, 0)
        self.github_repo_link = QLabel(
            f'<a href="https://github.com/{GITHUB_REPOSITORY}">{GITHUB_REPOSITORY}</a>'
        )
        self.github_repo_link.setObjectName("repositoryLink")
        self.github_repo_link.setOpenExternalLinks(True)
        self.github_repo_link.setToolTip("在浏览器中打开项目主页")
        update_grid.addWidget(self.github_repo_link, 1, 0)
        update_layout.addLayout(update_grid)
        self.github_auto_check = QCheckBox("启动时自动检查更新")
        self.github_auto_check.setChecked(True)
        update_layout.addWidget(self.github_auto_check)
        update_actions = QHBoxLayout()
        self.check_update_button = QPushButton("手动检查更新")
        self.check_update_button.setObjectName("primaryButton")
        self.open_release_button = QPushButton("打开 Release 页面")
        self.open_release_button.setEnabled(False)
        update_actions.addWidget(self.check_update_button)
        update_actions.addWidget(self.open_release_button)
        update_actions.addStretch(1)
        update_layout.addLayout(update_actions)
        self.update_status = QLabel("启动后会自动检查当前项目的 Latest Release。")
        self.update_status.setObjectName("cardHint")
        self.update_status.setWordWrap(True)
        update_layout.addWidget(self.update_status)
        layout.addWidget(update_card)

        diagnostic_card = Card()
        diagnostic_layout = QVBoxLayout(diagnostic_card)
        diagnostic_layout.setContentsMargins(24, 22, 24, 24)
        diagnostic_layout.setSpacing(14)
        diagnostic_layout.addLayout(
            self._card_heading(
                "本地错误日志",
                "发生错误时会写入本机；不会自动上传或发送。生成 ZIP 时会附带最近的识别诊断，请在发送前确认画面内容。",
            )
        )
        local_hint = QLabel(f"日志目录：{LOG_DIR}\n识别诊断目录：{VISION_DIAGNOSTICS_DIR}")
        local_hint.setObjectName("helper")
        local_hint.setWordWrap(True)
        local_hint.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        diagnostic_layout.addWidget(local_hint)
        diagnostic_actions = QHBoxLayout()
        self.create_bundle_button = QPushButton("生成可发送的诊断包")
        self.create_bundle_button.setObjectName("primaryButton")
        self.open_log_button = QPushButton("打开日志目录")
        diagnostic_actions.addWidget(self.create_bundle_button)
        diagnostic_actions.addWidget(self.open_log_button)
        diagnostic_actions.addStretch(1)
        diagnostic_layout.addLayout(diagnostic_actions)
        self.diagnostic_status = QLabel("诊断包只保存在本机，不会自动发送；完整画面可能包含角色名或聊天内容。")
        self.diagnostic_status.setObjectName("cardHint")
        self.diagnostic_status.setWordWrap(True)
        diagnostic_layout.addWidget(self.diagnostic_status)
        layout.addWidget(diagnostic_card)
        layout.addStretch(1)
        scroll.setWidget(canvas)
        return scroll

    @staticmethod
    def _card_heading(title: str, hint: str = "") -> QVBoxLayout:
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

    @staticmethod
    def _form_label(title: str, hint: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("formLabel")
        hint_label = QLabel(hint)
        hint_label.setObjectName("helper")
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        return widget

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

    def _populate_display_options(self) -> None:
        self.monitor_combo.clear()
        resolutions = ["1920 × 1080", "2560 × 1440", "3840 × 2160"]
        try:
            with mss.MSS() as screen:
                monitors = screen.monitors[1:]
            for index, monitor in enumerate(monitors, start=1):
                width, height = int(monitor["width"]), int(monitor["height"])
                resolution = f"{width} × {height}"
                self.monitor_combo.addItem(f"显示器 {index}  ·  {resolution}", index)
                if resolution not in resolutions:
                    resolutions.insert(0, resolution)
        except Exception:
            self.monitor_combo.addItem("显示器 1", 1)
        self.resolution_combo.clear()
        self.resolution_combo.addItems(resolutions)
        self._refresh_target_windows()

    def _refresh_target_windows(self, *_: object) -> None:
        config = self.engine.config()
        current_handle = config.target_window_handle
        current_title = config.target_window_title
        blocker = QSignalBlocker(self.target_window_combo)
        self.target_window_combo.clear()
        try:
            windows = window_target.list_target_windows()
        except Exception as error:  # pragma: no cover - 由 Windows 会话状态决定
            windows = []
            self.target_mode_status.setText(f"无法读取窗口列表：{error}")
        windows = [target for target in windows if target.title != self.windowTitle()]
        preferred_target = window_target.find_mabinogi_mobile_window(windows)
        self._auto_detected_game_window = preferred_target
        for target in windows:
            self.target_window_combo.addItem(
                f"{target.title}  ·  {target.width} × {target.height}", target
            )
        if self.target_window_combo.count() == 0:
            self.target_window_combo.addItem("未发现可选窗口，请打开洛奇 M 后刷新", None)
        if preferred_target is not None:
            self._select_target_window(preferred_target.handle, preferred_target.title)
        else:
            self._select_target_window(current_handle, current_title)
        del blocker
        if preferred_target is not None:
            self.engine.update_config(
                target_window_handle=preferred_target.handle,
                target_window_title=preferred_target.title,
            )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()

    def _select_target_window(self, handle: int, title: str) -> None:
        for index in range(self.target_window_combo.count()):
            target = self.target_window_combo.itemData(index)
            if not isinstance(target, window_target.WindowInfo):
                continue
            if target.handle == handle or (title and target.title == title):
                self.target_window_combo.setCurrentIndex(index)
                return

    def _sync_auto_roi_controls(self) -> None:
        automatic = self.auto_roi_check.isChecked()
        target = self.target_window_combo.currentData()
        has_target = isinstance(target, window_target.WindowInfo)
        self.resolution_combo.setEnabled(not automatic or not has_target)
        self.roi_width_spin.setEnabled(not automatic)
        self.roi_height_spin.setEnabled(not automatic)
        if not automatic:
            self.roi_mode_hint.setText(
                f"当前为手动模式：识别区域 {self.roi_width_spin.value()} × "
                f"{self.roi_height_spin.value()} px。"
            )
            return

        config = self.engine.config()
        source_resolution: tuple[int, int] | None = None
        source_text = "所选画面"
        if isinstance(target, window_target.WindowInfo):
            source_resolution = (target.width, target.height)
            profile_label = resolution_label_for_size(target.width, target.height)
            resolution_blocker = QSignalBlocker(self.resolution_combo)
            self._select_combo_text(self.resolution_combo, profile_label)
            del resolution_blocker
            if config.selected_resolution != profile_label:
                config = self.engine.update_config(
                    selected_resolution=profile_label
                )
            source_text = (
                f"已检测游戏窗口 {target.width} × {target.height}，"
                f"匹配 {profile_label}"
            )
        else:
            selected = self.resolution_combo.currentText()
            source_resolution = parse_resolution(selected)
            source_text = f"按所选画面 {selected}"

        roi_width, roi_height = effective_roi_size(config, source_resolution)
        width_blocker = QSignalBlocker(self.roi_width_spin)
        height_blocker = QSignalBlocker(self.roi_height_spin)
        self.roi_width_spin.setValue(roi_width)
        self.roi_height_spin.setValue(roi_height)
        del width_blocker, height_blocker
        self.roi_mode_hint.setText(
            f"{source_text}，识别区域自动设为 {roi_width} × {roi_height} px。"
        )

    def _auto_roi_toggled(self, checked: bool) -> None:
        if checked:
            self.engine.update_config(auto_scale_roi=True)
        else:
            self.engine.update_config(
                auto_scale_roi=False,
                roi_width=self.roi_width_spin.value(),
                roi_height=self.roi_height_spin.value(),
            )
        self._sync_auto_roi_controls()

    def _sync_target_mode_controls(self) -> None:
        is_window_mode = self.target_mode_combo.currentData() == "window"
        self.backend_options_panel.setProperty("modeActive", is_window_mode)
        self.backend_options_panel.setEnabled(is_window_mode)
        self.backend_mode_badge.setText(
            "● 后台设置已启用" if is_window_mode else "○ 当前为屏幕坐标模式"
        )
        for widget in [
            self.backend_options_panel,
            *self.backend_options_panel.findChildren(QWidget),
        ]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        if is_window_mode:
            target = self.target_window_combo.currentData()
            if isinstance(target, window_target.WindowInfo):
                if (
                    self._auto_detected_game_window is not None
                    and target.handle == self._auto_detected_game_window.handle
                ):
                    selection = f"已自动检测窗口名称“瑪奇 Mobile”：{target.title}。"
                else:
                    selection = f"当前手动目标：{target.title}。"
            else:
                selection = "未检测到“瑪奇 Mobile”，请从下拉列表选择游戏窗口。"
            backend = str(self.window_backend_combo.currentData())
            engine_text = (
                "OK 后台引擎：由 ok-script 提供 WGC 截图、虚拟悬停与 WM_ACTIVATE + PostMessage；"
                if backend == "ok"
                else "兼容引擎：使用 PrintWindow 截图与 WM_ACTIVATE + PostMessage；"
            )
            self.target_mode_status.setText(
                engine_text
                + "Space / W / S 和虚拟悬停只发送至这个窗口，真实鼠标可自由操作其他程序。"
                "请保持洛奇 M 窗口未最小化；临时错误会按设置重试，达到上限后暂停。"
                + selection
            )
        else:
            self.target_mode_status.setText(
                "稳定屏幕模式：识别与按键依赖洛奇 M 位于前台，不会在后台向其他窗口发送按键。"
            )

    def _target_mode_changed(self) -> None:
        self._sync_target_mode_controls()
        self._save_profile()

    def _load_config(self, config: AppConfig) -> None:
        controls = [
            self.monitor_combo,
            self.mode_combo,
            self.resolution_combo,
            self.target_mode_combo,
            self.window_backend_combo,
            self.target_window_combo,
            self.recognition_backend_combo,
            self.threshold_slider,
            self.auto_roi_check,
            self.roi_width_spin,
            self.roi_height_spin,
            self.interval_combo,
            self.trigger_spin,
            self.clear_spin,
            self.cooldown_spin,
            self.runtime_retry_spin,
            self.catch_strategy_combo,
            self.fallback_delay_spin,
            self.latest_collect_spin,
            self.stamina_zoom_spin,
            self.auto_resume_check,
            self.auto_recover_check,
            self.idle_min_spin,
            self.idle_max_spin,
            self.recovery_hold_spin,
            self.recovery_cooldown_spin,
            self.recovery_attempt_limit_spin,
            self.github_auto_check,
        ]
        blockers = [QSignalBlocker(control) for control in controls]
        self._select_combo_data(self.monitor_combo, config.monitor_index)
        self._select_combo_data(self.mode_combo, config.display_mode)
        self._select_combo_data(self.target_mode_combo, config.capture_mode)
        self._select_combo_data(self.window_backend_combo, config.window_backend)
        self._select_combo_data(
            self.recognition_backend_combo, config.recognition_backend
        )
        self._select_target_window(config.target_window_handle, config.target_window_title)
        self._select_combo_text(self.resolution_combo, config.selected_resolution)
        self.threshold_slider.setValue(config.fish_red_pixel_threshold)
        self.auto_roi_check.setChecked(config.auto_scale_roi)
        self.roi_width_spin.setValue(config.roi_width)
        self.roi_height_spin.setValue(config.roi_height)
        self._select_combo_data(self.interval_combo, config.poll_interval_ms)
        self.trigger_spin.setValue(config.trigger_consecutive_frames)
        self.clear_spin.setValue(config.clear_consecutive_frames)
        self.cooldown_spin.setValue(config.press_cooldown_ms)
        self.runtime_retry_spin.setValue(config.runtime_error_retry_count)
        self._select_combo_data(self.catch_strategy_combo, config.catch_strategy)
        self.fallback_delay_spin.setValue(config.fallback_collect_delay_seconds)
        self.latest_collect_spin.setValue(
            config.fixed_delay_latest_collect_seconds
        )
        self.stamina_zoom_spin.setValue(config.stamina_zoom_in_steps)
        self.auto_resume_check.setChecked(config.auto_resume_fishing)
        self.auto_recover_check.setChecked(config.auto_recover_idle)
        self.idle_min_spin.setValue(config.idle_red_pixel_min)
        self.idle_max_spin.setValue(config.idle_red_pixel_max)
        self.recovery_hold_spin.setValue(config.recovery_key_hold_ms)
        self.recovery_cooldown_spin.setValue(config.recovery_cooldown_ms)
        self.recovery_attempt_limit_spin.setValue(config.recovery_attempt_limit)
        self.github_auto_check.setChecked(config.github_auto_check)
        del blockers
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()
        self._sync_catch_strategy_controls()
        self._sync_recognition_backend_controls()
        self._refresh_threshold_display(config.fish_red_pixel_threshold)
    def _connect_controls(self) -> None:
        self.monitor_combo.currentIndexChanged.connect(self._save_profile)
        self.mode_combo.currentIndexChanged.connect(self._save_profile)
        self.resolution_combo.currentIndexChanged.connect(self._save_profile)
        self.target_mode_combo.currentIndexChanged.connect(self._target_mode_changed)
        self.window_backend_combo.currentIndexChanged.connect(self._target_mode_changed)
        self.target_window_combo.currentIndexChanged.connect(self._save_profile)
        self.refresh_windows_button.clicked.connect(self._refresh_target_windows)
        self.calibrate_button.clicked.connect(self._calibrate)
        self.start_button.clicked.connect(self._toggle_monitoring)
        self.snapshot_button.clicked.connect(self.engine.save_debug_capture)
        self.theme_button.clicked.connect(self._toggle_theme)
        self.recognition_backend_combo.currentIndexChanged.connect(
            self._recognition_backend_changed
        )
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        self.auto_roi_check.toggled.connect(self._auto_roi_toggled)
        self.roi_width_spin.valueChanged.connect(lambda value: self.engine.update_config(roi_width=value))
        self.roi_height_spin.valueChanged.connect(lambda value: self.engine.update_config(roi_height=value))
        self.interval_combo.currentIndexChanged.connect(
            lambda: self.engine.update_config(poll_interval_ms=int(self.interval_combo.currentData()))
        )
        self.trigger_spin.valueChanged.connect(
            lambda value: self.engine.update_config(trigger_consecutive_frames=value)
        )
        self.clear_spin.valueChanged.connect(
            lambda value: self.engine.update_config(clear_consecutive_frames=value)
        )
        self.cooldown_spin.valueChanged.connect(
            lambda value: self.engine.update_config(press_cooldown_ms=value)
        )
        self.runtime_retry_spin.valueChanged.connect(
            lambda value: self.engine.update_config(runtime_error_retry_count=value)
        )
        self.catch_strategy_combo.currentIndexChanged.connect(self._catch_strategy_changed)
        self.fallback_delay_spin.valueChanged.connect(
            self._fallback_delay_changed
        )
        self.latest_collect_spin.valueChanged.connect(
            self._latest_collect_changed
        )
        self.stamina_zoom_spin.valueChanged.connect(
            lambda value: self.engine.update_config(stamina_zoom_in_steps=value)
        )
        self.auto_resume_check.toggled.connect(
            lambda checked: self.engine.update_config(auto_resume_fishing=checked)
        )
        self.auto_recover_check.toggled.connect(
            lambda checked: self.engine.update_config(auto_recover_idle=checked)
        )
        self.idle_min_spin.valueChanged.connect(
            lambda value: self.engine.update_config(idle_red_pixel_min=value)
        )
        self.idle_max_spin.valueChanged.connect(
            lambda value: self.engine.update_config(idle_red_pixel_max=value)
        )
        self.recovery_hold_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_key_hold_ms=value)
        )
        self.recovery_cooldown_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_cooldown_ms=value)
        )
        self.recovery_attempt_limit_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_attempt_limit=value)
        )
        self.restore_button.clicked.connect(self._restore_recommended_settings)

        self.check_update_button.clicked.connect(lambda: self._check_for_updates(manual=True))
        self.github_auto_check.toggled.connect(
            lambda checked: self.engine.update_config(github_auto_check=checked)
        )
        self.open_release_button.clicked.connect(self._open_release_page)
        self.create_bundle_button.clicked.connect(self._create_diagnostic_bundle)
        self.open_log_button.clicked.connect(self._open_log_directory)
    def _catch_strategy_changed(self) -> None:
        self.engine.update_config(catch_strategy=str(self.catch_strategy_combo.currentData()))
        self._sync_catch_strategy_controls()

    def _fallback_delay_changed(self, value: float) -> None:
        self.engine.update_config(
            fallback_collect_delay_seconds=float(value)
        )
        if self.catch_strategy_combo.currentData() == "fixed_delay":
            self._sync_catch_strategy_controls()

    def _latest_collect_changed(self, value: float) -> None:
        self.engine.update_config(
            fixed_delay_latest_collect_seconds=float(value)
        )
        if self.catch_strategy_combo.currentData() == "fixed_delay":
            self._sync_catch_strategy_controls()

    def _sync_catch_strategy_controls(self) -> None:
        strategy = str(self.catch_strategy_combo.currentData())
        stack_index = {"stamina_bounce": 0, "fixed_delay": 1, "instant": 2}.get(strategy, 0)
        self.catch_option_stack.setCurrentIndex(stack_index)
        delay = float(self.fallback_delay_spin.value())
        latest = float(self.latest_collect_spin.value())
        effective = min(delay, latest)
        self.fixed_delay_effective_hint.setText(
            f"实际最晚会在上钩后 {effective:.1f} 秒按 Space；若目标更早消失，则按垃圾处理，不会拉钩。"
        )
        hints = {
            "stamina_bounce": "模式 1：先用 OK 特征确认中鱼图标并定位体力槽，再观察半条位置的小块颜色。连续变灰后不会收杆；只有再次连续恢复绿色才确认反弹。若识别失败后出现跑鱼提示，会学习本轮耗时并在下一轮提前 1–2 秒兜底。",
            "fixed_delay": f"模式 2（推荐）：目标仍存在时，等待 {delay:.1f} 秒收鱼，并以 {latest:.1f} 秒作为最迟拉钩上限；实际采用较早的 {effective:.1f} 秒。",
            "instant": "模式 3：只要识别到上钩鱼图标，立即按 Space 收杆。",
        }
        self.catch_strategy_hint.setText(hints.get(strategy, hints["stamina_bounce"]))
        self._sync_learned_escape_status()

    def _sync_learned_escape_status(self) -> None:
        learned = self.engine.config().learned_escape_seconds
        if learned <= 0:
            self.learned_escape_label.setText(
                "尚未学习。识别到“讓牠跑掉了”后会自动记录本轮耗时。"
            )
            return
        target, margin = FishingEngine.learned_collect_timing(learned)
        self.learned_escape_label.setText(
            f"上次跑鱼 {learned:.1f} 秒；识别仍失败时将在 "
            f"{target:.1f} 秒兜底（提前 {margin:.1f} 秒）。"
        )

    def _save_profile(self) -> None:
        config = self.engine.config()
        target = self.target_window_combo.currentData()
        target_handle = config.target_window_handle
        target_title = config.target_window_title
        if isinstance(target, window_target.WindowInfo):
            target_handle = target.handle
            target_title = target.title
        self.engine.update_config(
            monitor_index=int(self.monitor_combo.currentData() or 1),
            display_mode=str(self.mode_combo.currentData()),
            selected_resolution=self.resolution_combo.currentText(),
            capture_mode=str(self.target_mode_combo.currentData()),
            window_backend=str(self.window_backend_combo.currentData()),
            target_window_handle=target_handle,
            target_window_title=target_title,
        )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()
        self._refresh_calibration_summary()
    def _calibrate(self) -> None:
        self.calibration_summary.setText("校准待命：将鼠标停在钓鱼按钮正中心后按 F7，当前位置会立即记录，鼠标不会移动。")
        self._append_log("校准说明已显示：请把鼠标停在钓鱼按钮中心后按 F7；不要点击助手窗口来记录坐标。", EventKind.INFO)

    def _toggle_monitoring(self) -> None:
        self.engine.set_monitoring(not self.engine.is_monitoring())

    def _recognition_backend_changed(self) -> None:
        backend = str(self.recognition_backend_combo.currentData() or "ok")
        self.engine.update_config(recognition_backend=backend)
        self._sync_recognition_backend_controls()
        mode_name = "OK 框架特征识别" if backend == "ok" else "旧版像素识别"
        self._append_log(
            f"图标识别模式已切换为“{mode_name}”；两种模式不会自动互相回退。",
            EventKind.INFO,
        )

    def _sync_recognition_backend_controls(self) -> None:
        use_pixel = self.recognition_backend_combo.currentData() == "pixel"
        for control in (
            self.threshold_header_label,
            self.threshold_value,
            self.threshold_slider,
            self.idle_min_spin,
            self.idle_max_spin,
        ):
            control.setEnabled(use_pixel)
        if use_pixel:
            self.recognition_backend_hint.setText(
                "当前使用旧版像素兼容模式：根据红、白、绿、蓝、棕色像素判断图标；不会调用 OK 图标模板。"
            )
            self.red_metric.caption_label.setText("当前红色像素")
            self.red_metric.value_label.setText("0 px")
            self.red_progress.setMaximum(
                max(1, self.engine.config().fish_red_pixel_threshold)
            )
        else:
            self.recognition_backend_hint.setText(
                "当前使用 OK 框架：钓鱼、上钩和骑马图标由 FeatureSet 识别；旋转指南针单独使用中心黑点像素校正。"
            )
            self.red_metric.caption_label.setText("OK 特征相似度")
            self.red_metric.value_label.setText("等待识别")
            self.red_progress.setMaximum(1000)
        self.red_progress.setValue(0)

    def _threshold_changed(self, value: int) -> None:
        self.engine.update_config(fish_red_pixel_threshold=value)
        self._refresh_threshold_display(value)

    def _restore_recommended_settings(self) -> None:
        defaults = default_config()
        self.engine.update_config(
            recognition_backend=defaults.recognition_backend,
            roi_width=defaults.roi_width,
            roi_height=defaults.roi_height,
            auto_scale_roi=defaults.auto_scale_roi,
            poll_interval_ms=defaults.poll_interval_ms,
            fish_red_pixel_threshold=defaults.fish_red_pixel_threshold,
            idle_red_pixel_min=defaults.idle_red_pixel_min,
            idle_red_pixel_max=defaults.idle_red_pixel_max,
            trigger_consecutive_frames=defaults.trigger_consecutive_frames,
            clear_consecutive_frames=defaults.clear_consecutive_frames,
            press_cooldown_ms=defaults.press_cooldown_ms,
            runtime_error_retry_count=defaults.runtime_error_retry_count,
            auto_resume_fishing=defaults.auto_resume_fishing,
            auto_recover_idle=defaults.auto_recover_idle,
            recovery_consecutive_frames=defaults.recovery_consecutive_frames,
            recovery_key_hold_ms=defaults.recovery_key_hold_ms,
            recovery_pause_ms=defaults.recovery_pause_ms,
            recovery_cooldown_ms=defaults.recovery_cooldown_ms,
            recovery_attempt_limit=defaults.recovery_attempt_limit,
            catch_strategy=defaults.catch_strategy,
            fallback_collect_delay_seconds=defaults.fallback_collect_delay_seconds,
            fixed_delay_latest_collect_seconds=(
                defaults.fixed_delay_latest_collect_seconds
            ),
            stamina_scan_interval_ms=defaults.stamina_scan_interval_ms,
            stamina_zoom_in_steps=defaults.stamina_zoom_in_steps,
        )
        self._load_config(self.engine.config())
        self._append_log("已恢复推荐识别参数。", EventKind.INFO)

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
            record_error("collect system profile", error)
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

    def _save_update_preferences(self) -> None:
        # 仅固定更新源仓库；是否启动检查由用户的复选框决定。
        self.engine.update_config(github_repository=GITHUB_REPOSITORY)

    def _check_for_updates(self, *, manual: bool) -> None:
        self._save_update_preferences()
        repository = GITHUB_REPOSITORY
        self.check_update_button.setEnabled(False)
        self.update_status.setText("正在检查 GitHub Latest Release…")

        def worker() -> None:
            result = check_github_release(repository, APP_VERSION)
            if not result.ok:
                record_error(
                    "GitHub update check",
                    result.message,
                    extra={"repository": repository, "manual": manual},
                )
            self.update_ready.emit(result)

        threading.Thread(target=worker, name="github-update-check", daemon=True).start()

    def _show_update_result(self, result: object) -> None:
        self.check_update_button.setEnabled(True)
        if not isinstance(result, UpdateResult):
            self.update_status.setText("更新检查结果无效，详情已写入本地错误日志。")
            return
        self.update_status.setText(result.message)
        self._last_release_url = result.release_url
        self.open_release_button.setEnabled(bool(result.release_url))
        if result.ok:
            self._append_log(result.message, EventKind.INFO)
        if (
            result.update_available
            and result.latest_version
            and result.latest_version != self._notified_release_version
        ):
            self._notified_release_version = result.latest_version
            self._show_update_dialog(result)

    def _show_update_dialog(self, result: UpdateResult) -> None:
        if self._update_dialog is not None:
            self._update_dialog.close()
        dialog = UpdateAvailableDialog(result, self)
        self._update_dialog = dialog
        dialog.finished.connect(
            lambda _code, current=dialog: self._clear_update_dialog(current)
        )
        dialog.open()

    def _clear_update_dialog(self, dialog: UpdateAvailableDialog) -> None:
        if self._update_dialog is dialog:
            self._update_dialog = None

    def _open_release_page(self) -> None:
        if self._last_release_url:
            QDesktopServices.openUrl(QUrl(self._last_release_url))

    def _create_diagnostic_bundle(self) -> None:
        try:
            self.engine.export_diagnostic_snapshot("设置页手动生成")
            bundle_path = create_support_bundle()
        except OSError as error:
            record_error("create diagnostic bundle", error)
            self.diagnostic_status.setText("生成诊断包失败，详情已写入本地错误日志。")
            return
        QApplication.clipboard().setText(str(bundle_path))
        self.diagnostic_status.setText(
            f"已在本机生成诊断包，并将路径复制到剪贴板：{bundle_path}。请自行发送给项目维护者。"
        )
        self._append_log("已生成本地诊断包；不会自动上传。", EventKind.INFO)

    def _open_log_directory(self) -> None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOG_DIR)))

    def _toggle_theme(self) -> None:
        next_theme = "day" if self.engine.config().ui_theme == "night" else "night"
        self.engine.update_config(ui_theme=next_theme)
        self._apply_theme(next_theme)
        self._append_log(
            "已切换为日间界面。" if next_theme == "day" else "已切换为夜间界面。",
            EventKind.INFO,
        )

    def _apply_theme(self, theme: str) -> None:
        is_day = theme == "day"
        self.setStyleSheet(DAY_STYLE if is_day else NIGHT_STYLE)
        self.theme_button.setText("☾ 夜间模式" if is_day else "☀ 日间模式")
        self.theme_button.setToolTip("切换至夜间模式" if is_day else "切换至日间模式")

    def _refresh_calibration_summary(self) -> None:
        config = self.engine.config()
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
                self.runtime_detail.setText(
                    "正在识别指定窗口区域（实验性后台模式）。"
                    if self.engine.config().capture_mode == "window"
                    else "正在识别右下角圆形按钮。"
                )
                self.start_button.setText("暂停监测")
                self.start_button.setObjectName("dangerButton")
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
                self._set_status("running", "●  监测运行中")
                self._set_runtime_state("识别中", "running")
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

    def _set_runtime_state(self, text: str, state: str = "idle") -> None:
        self.runtime_state_chip.setProperty("state", state)
        self.runtime_state_chip.setText(f"状态 · {text}")
        self.runtime_state_chip.style().unpolish(self.runtime_state_chip)
        self.runtime_state_chip.style().polish(self.runtime_state_chip)

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

    def closeEvent(self, event: object) -> None:  # type: ignore[override]
        self.engine.close()
        event.accept()  # type: ignore[union-attr]
