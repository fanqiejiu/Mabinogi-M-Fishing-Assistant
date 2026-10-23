"""使用说明页面；钓鱼和制作操作文案"""
from __future__ import annotations
from fishing_assistant.desktop.design import configure_card_layout

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget
from fishing_assistant.desktop.widgets import Card


class HelpPageMixin:
    """使用说明页面；钓鱼和制作操作文案；由 MainWindow 组装，不单独实例化。"""

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
        layout.setSpacing(12)

        card = Card()
        card_layout = QVBoxLayout(card)
        configure_card_layout(card_layout)
        card_layout.setSpacing(12)
        card_layout.addLayout(self._card_heading("使用前说明"))
        steps = [
            "1. 钓鱼前务必将宠物卸下，再开始校准和监测。",
            "2. 控制台先确认目标游戏窗口；需手动调整显示器、画面模式或分辨率时，展开“画面配置”。",
            "3. 默认选择“后台运行（推荐）”；确认目标是“瑪奇 Mobile”。显示“已最小化”时恢复游戏后刷新窗口；游戏可被遮挡，但不能最小化。多开时请手动选择。",
            "4. 把鼠标停在右下角圆形钓鱼按钮的正中心，直接按 F7；不会弹出确认，也不会移动鼠标。",
            "5. 按 F9 保存识别现场，回到控制台点“查看截图”，确认圆形按钮没有被截断。",
            "6. 点击“开始监测”或按 F8；前台模式需保持游戏在前台。停止快捷键默认 Esc，可在“设置 → 常规 → 快捷键”修改或关闭；修改立即生效并自动保存。",
        ]
        for step in steps:
            label = QLabel(step)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            card_layout.addWidget(label)
        layout.addWidget(card)

        fishing_stats = Card()
        fishing_stats_layout = QVBoxLayout(fishing_stats)
        configure_card_layout(fishing_stats_layout)
        fishing_stats_layout.addLayout(self._card_heading("本次钓鱼记录"))
        fishing_stats_label = QLabel(
            "控制台和悬浮栏显示本次自动钓鱼的上鱼成功、普通成功和失败次数。上鱼成功指按下钓鱼键后"
            "进度条清空；普通成功指未检测到回弹、进度条自然流失清空；失败指检测到回弹并在填充宽度"
            "恢复至初始满格约九成后消失。"
            "三种收鱼模式共用现有体力条识别来判断结果，不增加新的画面识别区域。"
            "证据不足的轮次会提示且不计入，避免将识别漏帧误报成某一种结果。每次成功启动时本次计数清零。"
            "“钓鱼历史”保存启动/结束时间和各类次数，展示累计轮次、成功占比、已结束会话的总钓鱼时间及最近 100 条记录；"
            "数据仅保存在本机，不会上传；暂停时间包含在会话时长中，异常退出的未完成会话会标记为中断。"
        )
        fishing_stats_label.setWordWrap(True)
        fishing_stats_label.setObjectName("helpStep")
        fishing_stats_layout.addWidget(fishing_stats_label)
        layout.addWidget(fishing_stats)

        window_help = Card()
        window_layout = QVBoxLayout(window_help)
        configure_card_layout(window_layout)
        window_layout.setSpacing(9)
        window_layout.addLayout(self._card_heading("窗口与识别设置"))
        for text in (
            "运行方式：后台运行只操作选定窗口；前台运行捕获显示器画面并使用系统键鼠输入，必须保持游戏位于前台。切换后请重新校准。",
            "捕获方式：Windows Graphics Capture（WGC，默认）与 PrintWindow（兼容）只决定如何获取窗口画面。两者均使用窗口消息（PostMessage）输入，切换捕获方式不能解决所有按键无响应问题。",
            "图标识别：在“识别阈值”中选择图像模板匹配或像素识别（旧版兼容），与窗口捕获方式独立。图像模板匹配由 ok-script 的 FeatureSet 提供；旋转指南针保留中心黑点校正。识别失败不会自动切换方案。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            window_layout.addWidget(label)
        layout.addWidget(window_help)

        fishing_modes = Card()
        fishing_modes_layout = QVBoxLayout(fishing_modes)
        configure_card_layout(fishing_modes_layout)
        fishing_modes_layout.setSpacing(9)
        fishing_modes_layout.addLayout(
            self._card_heading(
                "钓鱼模式说明",
                "在“钓鱼设置 → 收鱼策略”中选择；三种模式只影响上钩后的收杆时机。",
            )
        )
        for text in (
            "模式 1 · 体力条反弹：确认中鱼图标并追踪角色头顶体力条，槽中点先变灰、再恢复绿色时收杆，对镜头和画面清晰度要求较高。若没有识别到反弹并出现跑鱼提示，会记录本轮上钩到跑鱼的时长 T；提前量为 T × 10%，但最少 1.0 秒、最多 2.0 秒，下一轮按 T − 提前量兜底。例如 14.0 秒跑鱼，会在 12.6 秒收杆；正常识别到反弹时不会等待计时。",
            "模式 2 · 定时收鱼（推荐）：目标仍存在时按自定义等待秒数收杆，并受“最迟收杆时间”限制，两者取较早的时间；目标提前消失则跳过。",
            "模式 3 · 上钩立即收杆：识别到上钩图标便立即按 Space，不判断体力条，因此也可能收起垃圾。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            fishing_modes_layout.addWidget(label)
        layout.addWidget(fishing_modes)

        cleanup_help = Card()
        cleanup_layout = QVBoxLayout(cleanup_help)
        configure_card_layout(cleanup_layout)
        cleanup_layout.addLayout(self._card_heading("背包清理与测试"))
        for text in (
            "在“钓鱼设置 → 背包清理”中启用“背包清理（实验性）”，背包满时会整理并继续钓鱼。默认关闭，启用前必须确认风险。",
            "清理会选择四类简单整理项目，并反复确认“大胆整理”已关闭。无法确认就停止，但仍可能误判并永久分解或出售物品。",
            "在“设置 → 调试”中可单独测试：先完成 F7 校准并停止当前任务，无需开启正式自动清理，也不会修改该开关。测试是真实清理，不是预览；开始前仍需确认风险。",
        ):
            label = QLabel(text)
            label.setObjectName("helpStep")
            label.setWordWrap(True)
            cleanup_layout.addWidget(label)
        layout.addWidget(cleanup_help)

        crafting_help = Card()
        crafting_layout = QVBoxLayout(crafting_help)
        configure_card_layout(crafting_layout)
        crafting_layout.addLayout(self._card_heading("自动制作", "木材、金属、布料、皮革按分类选择。"))
        for text in (
            "先在游戏里打开对应加工主界面和“全部”列表，再到“自动制作”选择材料和游戏窗口。制作固定使用 WGC 捕获与 PostMessage 输入，无需 F7，不受钓鱼窗口捕获选项影响；不要最小化游戏或切离加工界面。",
            "指定次数按加入队列的加工次数计算，不是产物件数。队列容量会从画面自动识别，新手可能只有 1 格，也可能是多行多格；木材每次 1分30秒，木材+每次 12分钟，时间按实际队列顺序预估。",
            "铁锭（矿石）、铁锭（铁矿石）各 1分钟，钢锭 10分钟；布料 1分30秒，丝绸 3分钟，布料+ 12分钟；皮革 1分钟，皮革+ 10分钟。时间仅用于预估，领取前必须识别到所有已占用格均为 100%。",
            "用完材料为止：按实际容量自动补满队列，出现材料不足后不再添加；已有项目完成并领取后停止。指定次数不足当前容量时只加需要的格数。开始前已有的项目会等待并领取，但不计入本次次数。",
            "制作与钓鱼、背包清理互斥。停止按钮、F8 或设置的停止快捷键会停止当前制作任务，但不取消游戏队列；停止后需要在制作页面重新开始，F8 启动的是钓鱼。",
            "“食物制作”是后续版本的预留子菜单，本版不能选择食谱或开始制作。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            crafting_layout.addWidget(label)
        layout.addWidget(crafting_help)

        floating_help = Card()
        floating_layout = QVBoxLayout(floating_help)
        configure_card_layout(floating_layout)
        floating_layout.addLayout(self._card_heading("后台悬浮栏 · 暂停与继续"))
        for text in (
            "后台运行并最小化助手后，悬浮栏显示校准和运行状态。点击“暂停”暂停当前任务，点击“继续”重新核对游戏画面后接续。可拖动空白处移动，在“设置 → 常规”中调整透明度或关闭悬浮栏。",
            "暂停的是助手，不是游戏。制作队列仍会计时；继续后保留本次次数，不重复添加已确认的材料。钓鱼会重新识别，暂停太久可能跑鱼。",
            "背包整理涉及物品处理：整理中点击暂停会安全停止，不能直接继续清理。F8 和设置的停止快捷键也属于停止，需要检查游戏页面后重新开始。",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setObjectName("helpStep")
            floating_layout.addWidget(label)
        layout.addWidget(floating_help)

        diagnostic_help = Card()
        diagnostic_help_layout = QVBoxLayout(diagnostic_help)
        configure_card_layout(diagnostic_help_layout)
        diagnostic_help_layout.setSpacing(9)
        diagnostic_help_layout.addLayout(self._card_heading("F9 · 保存识别现场"))
        for text in (
            "有什么用：保存按钮截图、完整画面和识别报告，方便排查图标漏识别、体力条不触发或分辨率不匹配；不是修复键，也不会替你重新校准。",
            "怎么用：先按 F7 校准；遇到问题时保留当时的游戏画面，按一次 F9。开始前或停止后也能保存；悬浮栏暂停期间需先停止任务，避免诊断改变待确认操作的悬停位置。",
            "前台模式：保持游戏在前台再按 F9，避免把助手窗口或其他程序截进去。后台模式：只读取选定窗口，游戏不能最小化。",
            "保存后：控制台会显示结果，可点“查看截图”检查按钮是否完整，或点“打开诊断目录”找到最新 ZIP。保存期间不会重复排队，F8 和设置的停止快捷键仍可使用。",
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
        configure_card_layout(hotkey_layout)
        hotkey_layout.addWidget(QLabel("全局快捷键"), 0, 0, 1, 2)
        hotkey_layout.itemAtPosition(0, 0).widget().setObjectName("cardTitle")
        for row, (key, description) in enumerate(
            (("F7", "立即记录当前鼠标位置为钓鱼按钮中心（不移动鼠标）"), ("F8", "开始钓鱼或停止当前任务"), ("F9", "保存识别区域与完整诊断包"), ("Esc", "紧急停止当前任务")),
            start=1,
        ):
            key_label = QLabel(key)
            key_label.setObjectName("shortcutKey")
            detail = QLabel(description)
            detail.setWordWrap(True)
            detail.setObjectName("cardHint")
            if key == "Esc":
                self.stop_hotkey_help_key = key_label
                self.stop_hotkey_help_detail = detail
            hotkey_layout.addWidget(key_label, row, 0)
            hotkey_layout.addWidget(detail, row, 1)
        layout.addWidget(hotkeys)
        layout.addStretch(1)
        scroll.setWidget(canvas)
        return scroll
