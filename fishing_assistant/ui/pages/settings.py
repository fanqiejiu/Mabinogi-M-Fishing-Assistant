"""应用设置标签页。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

from .base import BasePageMixin
from ..widget.card import Card
from ..widget.controls import ScrollSafeComboBox, ScrollSafeSlider
from ...constants import APP_NAME, APP_VERSION, GITHUB_REPOSITORY
from ...diagnostics import LOG_DIR, VISION_DIAGNOSTICS_DIR

class SettingsPageMixin(BasePageMixin):
    def _build_voice_alert_card(self) -> Card:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(11)
        layout.addLayout(
            self._card_heading(
                "语音提醒",
                "按操作和异常状态播放提示；后续新增人物文件夹后会自动出现在音色列表。",
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
        self.voice_character_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
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

    def _build_settings_page(self) -> QScrollArea:
        scroll, layout = BasePageMixin._new_page_canvas()

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
        layout.addWidget(self._build_voice_alert_card())

        floating_card = Card()
        floating_layout = QVBoxLayout(floating_card)
        floating_layout.setContentsMargins(24, 22, 24, 22)
        floating_layout.setSpacing(11)
        floating_layout.addLayout(
            self._card_heading(
                "后台悬浮状态栏",
                "使用指定窗口后台模式时，主界面最小化后显示校准和运行状态。",
            )
        )
        self.floating_status_check = QCheckBox(
            "最小化后显示始终置顶的状态栏"
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
        opacity_hint = QLabel("数值越高背景越实；文字始终保持清晰。")
        opacity_hint.setObjectName("helper")
        opacity_layout.addWidget(opacity_hint)
        floating_layout.addWidget(self.floating_opacity_panel)

        floating_hint = QLabel(
            "状态栏不会抢占当前程序焦点，可拖动到不遮挡游戏的位置；恢复助手窗口后会自动隐藏。"
            "其他游戏若使用独占全屏，Windows 可能覆盖普通置顶窗口，建议使用无边框模式。"
        )
        floating_hint.setObjectName("helper")
        floating_hint.setWordWrap(True)
        floating_layout.addWidget(floating_hint)
        layout.addWidget(floating_card)
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
        layout.addWidget(self._build_debug_section())

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
        return scroll

    def _build_debug_section(self) -> Card:
        debug_section = Card()
        debug_layout = QVBoxLayout(debug_section)
        debug_layout.setContentsMargins(24, 22, 24, 24)
        debug_layout.setSpacing(14)
        debug_layout.addLayout(
            self._card_heading(
                "调试",
                "用于单独验证实验功能；后续调试项目会集中放在这里。",
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
        option_hint = QLabel(
            "无需打开正式功能开关，可从当前游戏画面独立执行一次完整清理；完成后保持监测暂停。"
        )
        option_hint.setObjectName("helper")
        option_hint.setWordWrap(True)
        test_layout.addWidget(option_hint)
        danger = QLabel(
            "这不是识别预览：测试会真实分解或出售物品，也存在误用“大胆整理”的风险。"
        )
        danger.setObjectName("cardHint")
        danger.setWordWrap(True)
        test_layout.addWidget(danger)

        self.test_inventory_cleanup_button = QPushButton(
            "测试背包清理流程"
        )
        self.test_inventory_cleanup_button.setObjectName("dangerButton")
        test_layout.addWidget(self.test_inventory_cleanup_button)
        self.inventory_cleanup_test_status = QLabel(
            "无需启用“背包清理（实验性）”；完成 F7 校准后即可单独测试。"
        )
        self.inventory_cleanup_test_status.setObjectName("helper")
        self.inventory_cleanup_test_status.setWordWrap(True)
        test_layout.addWidget(self.inventory_cleanup_test_status)
        for text in (
            "1. 暂停普通监测，让角色停在可正常打开背包的画面。",
            "2. 不要提前打开背包；测试会从发送 I 键开始。",
            "3. 后台模式不会移动真实鼠标；屏幕模式会移动并点击游戏界面。",
            "4. 任一步超时或无法确认“大胆整理”关闭，测试会立即停止。",
        ):
            label = QLabel(text)
            label.setObjectName("helper")
            label.setWordWrap(True)
            test_layout.addWidget(label)
        debug_layout.addWidget(self.inventory_cleanup_debug_option)
        return debug_section

