"""应用主题和悬浮状态栏样式。"""

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
QFrame#debugOption {
    background: #0D192A; border: 1px solid #263A54; border-radius: 12px;
}
QLabel#debugOptionTitle { color: #EAF3FD; font-size: 14px; font-weight: 700; }
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
QLabel#brandMark { background: transparent; border: 0; }
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
QFrame#backendOptions, QFrame#strategyOption, QFrame#debugOption { background: #F8FBFE; border-color: #D4E0EC; }
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

FLOATING_NIGHT_STYLE = """
QWidget#floatingStatus { background: transparent; border: none; }
QLabel#floatingTitle { color: #F4F9FF; font-size: 12px; font-weight: 800; }
QLabel#floatingHint { color: #718AA7; font-size: 10px; }
QLabel#floatingState {
    background: #142338; border: 1px solid #2D4562; border-radius: 8px;
    color: #ADC1D8; padding: 7px 9px; font-size: 11px; font-weight: 700;
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
QLabel#floatingTitle { color: #172B45; font-size: 12px; font-weight: 800; }
QLabel#floatingHint { color: #71849A; font-size: 10px; }
QLabel#floatingState {
    background: #F0F5FA; border: 1px solid #CEDBE8; border-radius: 8px;
    color: #536B85; padding: 7px 9px; font-size: 11px; font-weight: 700;
}
QLabel#floatingState[state="running"] {
    background: #E0F7EE; border-color: #8DDBC0; color: #187352;
}
QLabel#floatingState[state="warning"] {
    background: #FFF5D8; border-color: #EDD38B; color: #86620B;
}
"""
