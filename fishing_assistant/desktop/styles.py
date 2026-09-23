"""日间、夜间和悬浮状态栏样式；只定义样式字符串。"""
from __future__ import annotations

from fishing_assistant.constants import resource_path
from fishing_assistant.desktop.design import TYPOGRAPHY_STYLE, FLOATING_TYPOGRAPHY_STYLE

_CHECKMARK = resource_path("fishing_assistant", "assets", "checkmark.svg").as_posix()
_CHEVRON_DOWN = resource_path("fishing_assistant", "assets", "chevron-down.svg").as_posix()
_CHEVRON_UP = resource_path("fishing_assistant", "assets", "chevron-up.svg").as_posix()




NIGHT_STYLE = """
QMainWindow { background: #09111F; color: #F7FAFC; }
QDialog, QMessageBox { background: #111D2F; color: #EEF4FB; }
QMessageBox QLabel { color: #EEF4FB; background: transparent; }
QDialog#updateDialog { background: #111D2F; }
QWidget { color: #EEF4FB; }
QFrame#sidebar { background: #0D1728; border-right: 1px solid #1E2B3E; }
QFrame#contentSurface { background: #09111F; }
QFrame#card, QFrame#metricCard {
    background: #111D2F;
    border: 1px solid #22324A;
    border-radius: 10px;
}
QFrame#metricCard { border-radius: 12px; background: #0D192A; }
QFrame#backendOptions, QFrame#strategyOption {
    background: #0D192A; border: 1px solid #263A54; border-radius: 10px;
}
QFrame#debugOption {
    background: #0D192A; border: 1px solid #263A54; border-radius: 12px;
}
QLabel#debugOptionTitle { color: #EAF3FD; font-weight: 700; }
QFrame#backendOptions[modeActive="true"] { background: #102A31; border-color: #2DB88B; }
QFrame#backendOptions[modeActive="true"] QLabel#formLabel { color: #E8FFF7; }
QFrame#backendOptions[modeActive="true"] QLabel#helper { color: #94C9B8; }
QLabel#backendModeBadge { color: #75E4BE; font-weight: 700; }
QFrame#backendOptions:disabled { background: #0A1423; border-color: #1C2A3D; }
QFrame#backendOptions QLabel:disabled { color: #5E728A; }
QFrame#backendOptions QComboBox:disabled, QFrame#backendOptions QPushButton:disabled {
    background: #0A1423; border-color: #203047; color: #5E728A;
}
QLabel#eyebrow { color: #7F9BBC; font-weight: 700; letter-spacing: 1px; }
QLabel#pageTitle { color: #F8FBFF; font-weight: 700; }
QLabel#pageSubtitle { color: #91A5BF; }
QLabel#cardTitle { color: #F7FAFC; font-weight: 700; }
QLabel#cardHint, QLabel#helper { color: #8296B0; }
QLabel#metricValue { color: #F9FCFF; font-weight: 700; }
QLabel#metricCaption { color: #8296B0; }
QLabel#formLabel { color: #DDE8F5; font-weight: 700; }
QLabel#safetyWarning { color: #FFB7A5; }
QToolButton#detailsToggle { color: #ABC1DA; background: transparent; border: 1px solid transparent; border-radius: 4px; padding: 5px; }
QToolButton#detailsToggle:hover, QToolButton#detailsToggle:focus { background: #21354E; border-color: #45627F; }
QToolTip { background: #17263A; color: #EEF4FB; border: 1px solid #45627F; padding: 6px; }
QLabel#helpStep { color: #C6D6E7; padding: 7px 0; }
QLabel#brandMark {
    background: transparent; border: 0;
}
QLabel#brandTitle { color: #F7FAFC; font-weight: 700; }
QLabel#brandSubtitle { color: #6F86A5; font-weight: 700; letter-spacing: 1.2px; }
QLabel#statusChip {
    background: #1B293C; border: 1px solid #2B3D56; border-radius: 14px;
    color: #AABCD2; padding: 6px 11px; font-weight: 700;
}
QLabel#statusChip[state="running"] { background: #123629; border-color: #1F7556; color: #80E7BF; }
QLabel#statusChip[state="warning"] { background: #3A2C14; border-color: #82631F; color: #F6CF6A; }
QLabel#runtimeStateChip {
    background: #0D192A; border: 1px solid #29415E; border-radius: 10px;
    color: #AFC3DA; padding: 9px 12px; font-weight: 700;
}
QLabel#runtimeStateChip[state="running"] { background: #102A31; border-color: #2DB88B; color: #75E4BE; }
QLabel#runtimeStateChip[state="warning"] { background: #3A2C14; border-color: #82631F; color: #F6CF6A; }
QPushButton#floatingStatusButton {
    background: #1B293C; border: 1px solid #2B3D56; border-radius: 10px;
    color: #AABCD2; padding: 8px 12px; font-weight: 700;
}
QPushButton#floatingStatusButton:hover { background: #21354E; border-color: #45627F; }
QPushButton#floatingStatusButton:checked {
    background: #123629; border-color: #1F7556; color: #80E7BF;
}
QPushButton#floatingStatusButton:checked:hover {
    background: #174634; border-color: #2DB88B;
}
QPushButton#floatingStatusButton:pressed { background: #132033; }
QFrame#timingCallout { background: #0A1626; border: 1px solid #29415E; border-radius: 9px; }
QLabel#timingTitle { color: #75E4BE; font-weight: 800; }
QLabel#updateDialogTitle { color: #F8FBFF; font-weight: 800; }
QLabel#updateDialogVersion { color: #75E4BE; font-weight: 700; }
QTextBrowser#releaseNotes {
    background: #0A1626; border: 1px solid #29415E; border-radius: 9px;
    color: #C8D6E6; padding: 9px; 
}
QPushButton#navButton {
    background: transparent; border: 0; border-left: 3px solid transparent;
    border-radius: 6px; color: #8EA2BD; text-align: left;
    padding: 7px 12px; font-weight: 600;
}
QPushButton#navButton:hover { background: #16263B; color: #EDF6FF; }
QPushButton#navButton:checked { background: #173A37; color: #77E4BE; border-left-color: #77E4BE; }
QPushButton#navButton:focus:!checked { background: #16263B; color: #EDF6FF; }
QLabel#navSection { color: #8296B0; padding: 6px 14px; }
QFrame#sectionDivider { background: #22324A; border: 0; max-height: 1px; }
QPushButton { border: 1px solid #30455F; background: #17263A; border-radius: 7px; padding: 8px 13px; color: #DCE8F4; font-weight: 600; }
QPushButton:hover { background: #21354E; border-color: #45627F; }
QPushButton:pressed { background: #132033; }
QPushButton#primaryButton { background: #1CB984; color: #06130F; border: 1px solid #42D4A4; }
QPushButton#primaryButton:hover { background: #39D3A1; border-color: #7DEAC6; }
QPushButton#dangerButton { background: #3B2930; border-color: #6B3E4D; color: #FDB5BF; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background: #0B1626; border: 1px solid #2B405B; border-radius: 9px;
    padding: 7px 10px; min-height: 20px; color: #EDF5FE;
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
QPlainTextEdit { background: #0A1423; border: 1px solid #233650; border-radius: 10px; padding: 10px; color: #AFC4DC; }
QScrollArea, QWidget#pageCanvas { border: 0; background: #09111F; }
QScrollBar:vertical { background: #0C1727; width: 11px; margin: 4px 2px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #3A526F; border-radius: 4px; min-height: 34px; }
QScrollBar::handle:vertical:hover { background: #567394; }
QScrollBar::handle:vertical:pressed { background: #6B8BAD; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

# 使用矢量对钩，不依赖 Windows 字体是否提供特殊字符。
NIGHT_STYLE += 'QCheckBox::indicator:checked { image: url("' + _CHECKMARK + '"); }'
NIGHT_STYLE += (
    'QComboBox::down-arrow, QSpinBox::down-arrow, QDoubleSpinBox::down-arrow '
    '{ image: url("' + _CHEVRON_DOWN + '"); width: 10px; height: 10px; }'
    'QSpinBox::up-arrow, QDoubleSpinBox::up-arrow '
    '{ image: url("' + _CHEVRON_UP + '"); width: 10px; height: 10px; }'
)
NIGHT_STYLE += """
QCheckBox::indicator:hover { border-color: #7AA9CC; }
QCheckBox::indicator:checked { background: #15825E; border-color: #50CCA1; }
QCheckBox:disabled { color: #8397AC; }
QCheckBox::indicator:disabled { background: #243348; border-color: #50637A; }
QCheckBox::indicator:checked:disabled { background: #526B78; }
QLabel#fieldLabel { color: #DDE8F5; font-weight: 700; }
QLabel#availabilityBadge { color: #A5D5EF; font-weight: 700; }
QPushButton:disabled, QPushButton#primaryButton:disabled, QPushButton#dangerButton:disabled { background: #142033; border-color: #293C54; color: #71859D; }
QTabWidget#craftingHub::pane { border: 0; background: #09111F; }
QTabBar::tab { background: transparent; color: #ABC0D6; border: 0; border-bottom: 3px solid transparent; padding: 10px 16px; margin: 0 6px 0 0; }
QTabBar::tab:selected { color: #91F0C9; border-bottom-color: #36AD87; font-weight: 600; }
QTabBar::tab:hover { background: #16263B; }
QTabBar::tab:focus { background: #21354E; }
QTabWidget#craftingHub::pane { padding-top: 12px; }
"""

NIGHT_STYLE += TYPOGRAPHY_STYLE

DAY_STYLE = NIGHT_STYLE + """
QMainWindow, QFrame#contentSurface, QScrollArea, QWidget#pageCanvas { background: #F4F7FB; color: #172236; }
QDialog, QMessageBox { background: #FFFFFF; color: #1B2A40; }
QMessageBox QLabel { color: #1B2A40; background: transparent; }
QDialog#updateDialog { background: #FFFFFF; }
QWidget { color: #1B2A40; }
QFrame#sidebar { background: #FFFFFF; border-right-color: #D9E3EF; }
QFrame#card, QFrame#metricCard { background: #FFFFFF; border-color: #D7E2EE; }
QFrame#metricCard { background: #F8FBFE; }
QFrame#backendOptions, QFrame#strategyOption, QFrame#debugOption { background: #F8FBFE; border-color: #D4E0EC; }
QFrame#backendOptions[modeActive="true"] { background: #ECFAF5; border-color: #70CBAE; }
QFrame#backendOptions[modeActive="true"] QLabel#formLabel { color: #163F34; }
QFrame#backendOptions[modeActive="true"] QLabel#helper { color: #47776A; }
QLabel#backendModeBadge { color: #16835F; }
QFrame#backendOptions:disabled { background: #EEF3F8; border-color: #D9E3ED; }
QFrame#backendOptions QLabel:disabled { color: #8A9AAF; }
QFrame#backendOptions QComboBox:disabled, QFrame#backendOptions QPushButton:disabled {
    background: #EEF3F8; border-color: #D9E3ED; color: #8A9AAF;
}
QLabel#eyebrow, QLabel#brandSubtitle, QLabel#metricCaption, QLabel#cardHint, QLabel#helper, QLabel#pageSubtitle { color: #667B95; }
QLabel#pageTitle, QLabel#cardTitle, QLabel#metricValue, QLabel#brandTitle, QLabel#aboutVersion, QLabel#shortcutKey { color: #14233A; }
QLabel#statusChip { background: #EDF2F7; border-color: #D3DFEC; color: #556B85; }
QLabel#statusChip[state="running"] { background: #E0F7EE; border-color: #8DDBC0; color: #187352; }
QLabel#statusChip[state="warning"] { background: #FFF5D8; border-color: #EDD38B; color: #86620B; }
QLabel#runtimeStateChip { background: #F4F8FC; border-color: #C9D8E8; color: #536B85; }
QLabel#runtimeStateChip[state="running"] { background: #E0F7EE; border-color: #8DDBC0; color: #187352; }
QLabel#runtimeStateChip[state="warning"] { background: #FFF5D8; border-color: #EDD38B; color: #86620B; }
QPushButton#floatingStatusButton {
    background: #EDF2F7; border-color: #D3DFEC; color: #556B85;
}
QPushButton#floatingStatusButton:hover { background: #EAF1F8; border-color: #9CB6D1; }
QPushButton#floatingStatusButton:checked {
    background: #E0F7EE; border-color: #8DDBC0; color: #187352;
}
QPushButton#floatingStatusButton:checked:hover {
    background: #D4F2E5; border-color: #70CBAE;
}
QPushButton#floatingStatusButton:pressed { background: #DCE8F3; }
QFrame#timingCallout { background: #F4F9FC; border-color: #C9D8E8; }
QLabel#timingTitle { color: #16835F; }
QLabel#updateDialogTitle { color: #14233A; }
QLabel#updateDialogVersion { color: #16835F; }
QTextBrowser#releaseNotes { background: #F7FAFD; border-color: #C9D8E8; color: #304A66; }
QPushButton#navButton { color: #60758E; }
QPushButton#navButton:hover { background: #EDF3F8; color: #172C48; }
QPushButton#navButton:checked { background: #DDF5EA; color: #107450; border-left-color: #107450; }
QPushButton#navButton:focus:!checked { background: #EDF3F8; color: #172C48; }
QLabel#navSection { color: #667B95; }
QFrame#sectionDivider { background: #D7E2EE; }
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
QLabel#safetyWarning { color: #A23825; }
QToolButton#detailsToggle { color: #425C79; background: transparent; }
QToolButton#detailsToggle:hover, QToolButton#detailsToggle:focus { background: #EAF1F8; border-color: #9CB6D1; }
QToolTip { background: #FFFFFF; color: #263B55; border-color: #9CB6D1; }
QLabel#helpStep { color: #3D5774; }
QLabel#fieldLabel { color: #263B55; }
QLabel#debugOptionTitle { color: #203A56; }
QLabel#cardHint, QLabel#helper, QLabel#pageSubtitle { color: #526B84; }
QLabel#availabilityBadge { color: #315D80; }
QCheckBox::indicator { background: #FFFFFF; border-color: #829AAF; }
QCheckBox::indicator:hover { background: #EDF7F3; border-color: #16795B; }
QCheckBox::indicator:checked { background: #147451; border-color: #0C6343; }
QCheckBox:disabled { color: #718399; }
QCheckBox::indicator:disabled { background: #E4EAF0; border-color: #B4C1CF; }
QCheckBox::indicator:checked:disabled { background: #708498; border-color: #708498; }
QPushButton#primaryButton { background: #137451; border-color: #0F6347; color: #FFFFFF; }
QPushButton#primaryButton:hover { background: #0F6546; border-color: #0A5339; color: #FFFFFF; }
QPushButton:disabled, QPushButton#primaryButton:disabled, QPushButton#dangerButton:disabled { background: #EAF0F5; border-color: #CCD8E3; color: #75889B; }
QTabWidget#craftingHub::pane { background: #F4F7FB; }
QTabBar::tab { background: transparent; color: #48617A; border-bottom-color: transparent; }
QTabBar::tab:selected { color: #145B42; border-bottom-color: #16835F; }
QTabBar::tab:hover { background: #EDF3F8; }
QTabBar::tab:focus { background: #E4EEF7; }
"""

FLOATING_NIGHT_STYLE = """
QWidget#floatingStatus { background: transparent; border: none; }
QLabel#floatingTitle { color: #F4F9FF; font-weight: 800; }
QLabel#floatingHint { color: #718AA7; }
QLabel#floatingState {
    background: #142338; border: 1px solid #2D4562; border-radius: 8px;
    color: #ADC1D8; padding: 7px 9px; font-weight: 700;
}
QLabel#floatingState[state="running"] {
    background: #12352B; border-color: #287759; color: #80E7BF;
}
QLabel#floatingState[state="warning"] {
    background: #3A2C14; border-color: #82631F; color: #F6CF6A;
}
"""

FLOATING_DAY_STYLE = """
QWidget#floatingStatus { background: transparent; border: none; }
QLabel#floatingTitle { color: #172B45; font-weight: 800; }
QLabel#floatingHint { color: #71849A; }
QLabel#floatingState {
    background: #F0F5FA; border: 1px solid #CEDBE8; border-radius: 8px;
    color: #536B85; padding: 7px 9px; font-weight: 700;
}
QLabel#floatingState[state="running"] {
    background: #E0F7EE; border-color: #8DDBC0; color: #187352;
}
QLabel#floatingState[state="warning"] {
    background: #FFF5D8; border-color: #EDD38B; color: #86620B;
}
"""

FLOATING_NIGHT_STYLE += """
QPushButton { border-radius: 6px; padding: 0 8px; font-weight: 700; }
QPushButton#floatingPause { background: #E9B650; border: 1px solid #FFE09B; color: #231B08; }
QPushButton#floatingPause:hover { background: #F5CB76; border-color: #FFF0CB; }
QPushButton#floatingPause:pressed { background: #CA9636; }
QPushButton#floatingResume { background: #238460; border: 1px solid #73DDB1; color: #FFFFFF; }
QPushButton#floatingResume:hover { background: #2B9B71; border-color: #A9F2D2; }
QPushButton#floatingResume:pressed { background: #176A4B; }
QPushButton:disabled, QPushButton#floatingPause:disabled, QPushButton#floatingResume:disabled { background: #162334; border: 1px solid #304257; color: #718499; }
"""
FLOATING_DAY_STYLE += """
QLabel#floatingHint { color: #4D6680; }
QPushButton { border-radius: 6px; padding: 0 8px; font-weight: 700; }
QPushButton#floatingPause { background: #F1BF5A; border: 1px solid #B8882D; color: #352509; }
QPushButton#floatingPause:hover { background: #F8CF80; border-color: #86600E; }
QPushButton#floatingPause:pressed { background: #DCA337; }
QPushButton#floatingResume { background: #176D4D; border: 1px solid #0E593E; color: #FFFFFF; }
QPushButton#floatingResume:hover { background: #0F8058; border-color: #084C34; }
QPushButton#floatingResume:pressed { background: #0E553C; }
QPushButton:disabled, QPushButton#floatingPause:disabled, QPushButton#floatingResume:disabled { background: #E4EBF2; border: 1px solid #BECCDA; color: #7B8DA0; }
"""

# 悬浮栏保持紧凑，但不再使用 10px 的提示文字。
FLOATING_NIGHT_STYLE += FLOATING_TYPOGRAPHY_STYLE
FLOATING_DAY_STYLE += FLOATING_TYPOGRAPHY_STYLE
