"""使用说明标签页。"""
from PySide6.QtWidgets import *

from .base import BasePageMixin
from ..widget.card import Card
from ..widget.controls import ScrollSafeComboBox, ScrollSafeSlider

class HelpPageMixin(BasePageMixin):
    def _build_help_page(self) -> QScrollArea:
        scroll, layout = BasePageMixin._new_page_canvas()

        card = Card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 24)
        card_layout.setSpacing(12)
        card_layout.addLayout(self._card_heading("使用前说明", "一次正确校准比固定等待时间更可靠。"))
        steps = [
            "1. 钓鱼前务必将宠物卸下，再开始校准和监测。",
            "2. 在游戏内确认分辨率和画面模式，然后在“控制台”中选择对应配置。",
            "3. 默认使用“指定窗口后台模式（推荐）”；确认目标是“瑪奇 Mobile”，找不到时手动选择。",
            "4. 把鼠标停在右下角圆形钓鱼按钮的正中心，直接按 F7；不会弹出确认，也不会移动鼠标。",
            "5. 按 F9 保存识别现场，回到控制台点“查看截图”，确认圆形按钮没有被截断。",
            "6. 点击“开始监测”或按 F8；前台模式需保持游戏在前台，Esc 会紧急停止监测。",
        ]
        for step in steps:
            label = QLabel(step)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            card_layout.addWidget(label)
        layout.addWidget(card)

        fishing_modes = Card()
        fishing_modes_layout = QVBoxLayout(fishing_modes)
        fishing_modes_layout.setContentsMargins(24, 22, 24, 24)
        fishing_modes_layout.setSpacing(9)
        fishing_modes_layout.addLayout(
            self._card_heading(
                "钓鱼模式说明",
                "在“钓鱼设置”中选择；三种模式只影响上钩后的收杆时机。",
            )
        )
        for text in (
            "模式 1 · 体力条反弹：确认中鱼图标并追踪角色头顶体力条，槽中点先变灰、再恢复绿色时收杆，对镜头和画面清晰度要求较高。若没有识别到反弹并出现跑鱼提示，会记录本轮上钩到跑鱼的时长 T；提前量为 T × 10%，但最少 1.0 秒、最多 2.0 秒，下一轮按 T − 提前量兜底。例如 14.0 秒跑鱼，会在 12.6 秒收杆；正常识别到反弹时不会等待计时。",
            "模式 2 · 定时收鱼（推荐）：目标仍存在时按自定义等待秒数收杆，并受“最迟空格拉钩秒数”限制，适合优先稳定挂机。",
            "模式 3 · 上钩立即收杆：识别到上钩图标便立即按 Space，不判断体力条，因此也可能收起垃圾。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            fishing_modes_layout.addWidget(label)
        layout.addWidget(fishing_modes)

        diagnostic_help = Card()
        diagnostic_help_layout = QVBoxLayout(diagnostic_help)
        diagnostic_help_layout.setContentsMargins(24, 22, 24, 24)
        diagnostic_help_layout.setSpacing(9)
        diagnostic_help_layout.addLayout(self._card_heading("F9 · 保存识别现场"))
        for text in (
            "有什么用：保存按钮截图、完整画面和识别报告，方便排查图标漏识别、体力条不触发或分辨率不匹配；不是修复键，也不会替你重新校准。",
            "怎么用：先按 F7 校准；遇到问题时保留当时的游戏画面，按一次 F9。开始前或暂停后也能保存，无需按 F8。",
            "前台模式：保持游戏在前台再按 F9，避免把助手窗口或其他程序截进去。后台模式：只读取选定窗口，游戏不能最小化。",
            "保存后：控制台会显示结果，可点“查看截图”检查按钮是否完整，或点“打开诊断目录”找到最新 ZIP。保存期间不会重复排队，F8 / Esc 仍可使用。",
            "文件内容：ZIP 内的 roi.png 是识别区域，frame.png 是同一时刻的完整画面，report.json 是分辨率、校准位置与分层识别报告。每次按时间分别保存，不覆盖上一次。",
            "隐私提醒：文件仅保存在本机，不会自动上传。前台模式会截取所选显示器，分享 ZIP 前请检查角色名、聊天和其他不想公开的内容。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            diagnostic_help_layout.addWidget(label)
        layout.addWidget(diagnostic_help)

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
            detail.setWordWrap(True)
            detail.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Preferred,
            )
            hotkey_layout.addWidget(key_label, row, 0)
            hotkey_layout.addWidget(detail, row, 1)
        layout.addWidget(hotkeys)
        layout.addStretch(1)
        return scroll

