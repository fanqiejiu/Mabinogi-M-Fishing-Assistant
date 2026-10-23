"""应用设置、语音、诊断信息与调试区域布局"""
from __future__ import annotations
from fishing_assistant.desktop.design import configure_card_layout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from fishing_assistant.constants import (
    APP_NAME,
    APP_VERSION,
    GITHUB_REPOSITORY,
    REMOTE_PREVIEW_ENABLED,
)
from fishing_assistant.config import STOP_HOTKEY_LABELS
from fishing_assistant.desktop.widgets import Card, DetailsPanel, ScrollSafeComboBox, ScrollSafeSlider
from fishing_assistant.desktop.pages.sectioned import SectionedPage
from fishing_assistant.diagnostics import LOG_DIR, VISION_DIAGNOSTICS_DIR


class SettingsPageMixin:
    """应用设置、语音、诊断信息与调试区域布局；由 MainWindow 组装，不单独实例化。"""

    def _build_hotkey_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.addLayout(self._card_heading("快捷键"))
        row = QHBoxLayout()
        label = QLabel("停止快捷键")
        label.setObjectName("formLabel")
        row.addWidget(label)
        self.stop_hotkey_combo = ScrollSafeComboBox()
        self.stop_hotkey_combo.setAccessibleName("停止快捷键")
        for key, title in STOP_HOTKEY_LABELS.items():
            self.stop_hotkey_combo.addItem(title + ("（默认）" if key == "esc" else ""), key)
        self.stop_hotkey_combo.setToolTip(
            "全局停止当前钓鱼、制作或背包测试；修改后立即生效。"
            "在其他游戏中常用 Esc 时，请改键或选择“不启用”。F7 / F8 / F9 保留原功能。"
        )
        row.addWidget(self.stop_hotkey_combo, 1)
        layout.addLayout(row)
        hint = QLabel("F8 始终保留开始 / 停止功能。")
        hint.setObjectName("helper")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    def _build_hardware_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
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

    def _build_voice_alert_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        configure_card_layout(layout)
        layout.setSpacing(11)
        layout.addLayout(
            self._card_heading(
                "语音提醒",
            )
        )

        self.voice_alerts_check = QCheckBox("启用语音提醒")
        self.voice_alerts_check.setChecked(True)
        layout.addWidget(self.voice_alerts_check)

        selection = QHBoxLayout()
        selection.setSpacing(10)
        voice_label = QLabel("提醒音色")
        voice_label.setObjectName("formLabel")
        selection.addWidget(voice_label)
        self.voice_character_combo = ScrollSafeComboBox()
        self.voice_character_combo.setMinimumWidth(180)
        for character in self.voice_player.available_characters():
            self.voice_character_combo.addItem(character, character)
        if self.voice_character_combo.count() == 0:
            self.voice_character_combo.addItem("未找到可用音色", "")
        selection.addWidget(self.voice_character_combo, 1)
        self.voice_preview_button = QPushButton("试听")
        selection.addWidget(self.voice_preview_button)
        layout.addLayout(selection)

        self.voice_status = QLabel()
        self.voice_status.setObjectName("helper")
        self.voice_status.setWordWrap(True)
        layout.addWidget(self.voice_status)
        return card

    def _build_settings_page(self) -> SectionedPage:
        scroll = SectionedPage()
        general = scroll.add_section("general", "常规")
        updates = scroll.add_section("updates", "更新与关于")
        diagnostics = scroll.add_section("diagnostics", "诊断")
        debug = scroll.add_section("debug", "调试")

        identity = Card()
        identity_layout = QVBoxLayout(identity)
        configure_card_layout(identity_layout)
        identity_layout.setSpacing(7)
        identity_layout.addLayout(self._card_heading("关于"))
        version = QLabel(f"{APP_NAME}  ·  v{APP_VERSION}")
        version.setObjectName("aboutVersion")
        version.setWordWrap(True)
        identity_layout.addWidget(version)
        ok_credit = QLabel(
            '自动化框架：<a href="https://github.com/ok-oldking/ok-script">ok-script</a> '
            '（Apache-2.0 + Commons Clause）。'
        )
        ok_credit.setObjectName("cardHint")
        ok_credit.setOpenExternalLinks(True)
        ok_credit.setWordWrap(True)
        identity_layout.addWidget(ok_credit)
        updates.addWidget(identity)
        if REMOTE_PREVIEW_ENABLED:
            from fishing_assistant.remote_ui import RemotePanel
            self.remote_panel = RemotePanel(self.engine)
            general.addWidget(self.remote_panel)
        general.addWidget(self._build_hotkey_card())
        general.addWidget(self._build_voice_alert_card())

        floating_card = Card()
        floating_layout = QVBoxLayout(floating_card)
        configure_card_layout(floating_layout)
        floating_layout.setSpacing(11)
        floating_layout.addLayout(
            self._card_heading(
                "悬浮状态栏",
                "后台运行时，助手最小化后显示校准和运行状态。",
            )
        )
        self.floating_status_check = QCheckBox(
            "最小化助手后显示置顶状态栏"
        )
        self.floating_status_check.setChecked(True)
        floating_layout.addWidget(self.floating_status_check)

        self.floating_opacity_panel = QWidget()
        opacity_layout = QVBoxLayout(self.floating_opacity_panel)
        opacity_layout.setContentsMargins(0, 2, 0, 2)
        opacity_layout.setSpacing(7)
        opacity_header = QHBoxLayout()
        opacity_title = QLabel("背景不透明度")
        opacity_title.setObjectName("formLabel")
        self.floating_opacity_value = QLabel("92%")
        self.floating_opacity_value.setObjectName("helper")
        opacity_header.addWidget(opacity_title)
        opacity_header.addStretch(1)
        opacity_header.addWidget(self.floating_opacity_value)
        opacity_layout.addLayout(opacity_header)
        self.floating_opacity_slider = ScrollSafeSlider(
            Qt.Orientation.Horizontal
        )
        self.floating_opacity_slider.setRange(35, 100)
        self.floating_opacity_slider.setSingleStep(1)
        self.floating_opacity_slider.setPageStep(5)
        self.floating_opacity_slider.setValue(92)
        self.floating_opacity_slider.setToolTip(
            "只调整悬浮栏底色，文字和状态颜色不会变淡"
        )
        opacity_layout.addWidget(self.floating_opacity_slider)
        floating_layout.addWidget(self.floating_opacity_panel)

        self.floating_status_check.setToolTip(
            "状态栏不会抢占当前程序焦点，可拖动到不遮挡游戏的位置；恢复助手窗口后会自动隐藏。"
            "其他游戏若使用独占全屏，Windows 可能覆盖普通置顶窗口，建议使用无边框模式。"
        )
        general.addWidget(floating_card)
        diagnostics.addWidget(self._build_hardware_card())

        update_card = Card()
        update_layout = QVBoxLayout(update_card)
        configure_card_layout(update_layout)
        update_layout.setSpacing(14)
        update_layout.addLayout(
            self._card_heading(
                "软件更新",
                "更新源固定为本项目仓库；可选择是否在启动时自动检查。",
            )
        )
        update_grid = QGridLayout()
        update_grid.setHorizontalSpacing(18)
        update_grid.setVerticalSpacing(7)
        update_grid.addWidget(self._form_label("项目主页", "更新源固定为当前项目"), 0, 0)
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
        self.check_update_button = QPushButton("检查更新")
        self.check_update_button.setObjectName("primaryButton")
        self.open_release_button = QPushButton("查看发布页")
        self.open_release_button.setEnabled(False)
        update_actions.addWidget(self.check_update_button)
        update_actions.addWidget(self.open_release_button)
        update_actions.addStretch(1)
        update_layout.addLayout(update_actions)
        self.update_status = QLabel("尚未检查更新")
        self.update_status.setObjectName("cardHint")
        self.update_status.setWordWrap(True)
        update_layout.addWidget(self.update_status)
        updates.insertWidget(0, update_card)
        debug.addWidget(self._build_debug_section())

        diagnostic_card = Card()
        diagnostic_layout = QVBoxLayout(diagnostic_card)
        configure_card_layout(diagnostic_layout)
        diagnostic_layout.setSpacing(14)
        diagnostic_layout.addLayout(
            self._card_heading(
                "日志与诊断",
                "发生错误时会写入本机；不会自动上传或发送。生成 ZIP 时会附带最近的识别诊断，请在发送前确认画面内容。",
            )
        )
        diagnostic_actions = QHBoxLayout()
        self.create_bundle_button = QPushButton("导出诊断包")
        self.create_bundle_button.setObjectName("primaryButton")
        self.open_log_button = QPushButton("打开日志目录")
        self.open_log_button.setToolTip(f"日志：{LOG_DIR}\n识别诊断：{VISION_DIAGNOSTICS_DIR}")
        diagnostic_actions.addWidget(self.create_bundle_button)
        diagnostic_actions.addWidget(self.open_log_button)
        diagnostic_actions.addStretch(1)
        diagnostic_layout.addLayout(diagnostic_actions)
        self.diagnostic_status = QLabel("仅保存到本机；分享前请检查截图中的角色名和聊天内容。")
        self.diagnostic_status.setObjectName("cardHint")
        self.diagnostic_status.setWordWrap(True)
        diagnostic_layout.addWidget(self.diagnostic_status)
        diagnostics.addWidget(diagnostic_card)
        return scroll

    def _build_debug_section(self) -> Card:
        debug_section = Card()
        debug_layout = QVBoxLayout(debug_section)
        configure_card_layout(debug_layout)
        debug_layout.setSpacing(14)
        debug_layout.addLayout(
            self._card_heading(
                "调试",
            )
        )

        self.inventory_cleanup_debug_option = QFrame()
        self.inventory_cleanup_debug_option.setObjectName("debugOption")
        test_layout = QVBoxLayout(self.inventory_cleanup_debug_option)
        test_layout.setContentsMargins(18, 16, 18, 18)
        test_layout.setSpacing(10)
        option_title = QLabel("背包清理测试")
        option_title.setObjectName("debugOptionTitle")
        test_layout.addWidget(option_title)
        danger = QLabel(
            "这不是识别预览：测试会真实分解或出售物品，也存在误用“大胆整理”的风险。"
        )
        danger.setObjectName("safetyWarning")
        danger.setWordWrap(True)
        test_layout.addWidget(danger)

        self.test_inventory_cleanup_button = QPushButton(
            "测试背包清理"
        )
        self.test_inventory_cleanup_button.setObjectName("dangerButton")
        test_layout.addWidget(self.test_inventory_cleanup_button)
        self.inventory_cleanup_test_status = QLabel(
            "请先完成 F7 校准。"
        )
        self.inventory_cleanup_test_status.setObjectName("helper")
        self.inventory_cleanup_test_status.setWordWrap(True)
        test_layout.addWidget(self.inventory_cleanup_test_status)
        test_layout.addWidget(DetailsPanel("测试前准备", (
            "1. 停止当前任务，让角色停在可正常打开背包的画面。",
            "2. 无需提前打开背包，测试会识别当前页面并进入清理。",
            "3. 后台运行不移动系统鼠标；前台运行会移动并点击游戏界面。",
            "4. 任一步超时或无法确认“大胆整理”关闭，测试会立即停止。",
        )))
        debug_layout.addWidget(self.inventory_cleanup_debug_option)
        return debug_section
