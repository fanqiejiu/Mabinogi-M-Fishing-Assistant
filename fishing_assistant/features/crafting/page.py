"""自动制作页面：分类选材、次数计划、动态多行进度。"""
from __future__ import annotations
from fishing_assistant.desktop.design import configure_card_layout
from PySide6.QtCore import QSignalBlocker, QTimer, Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from datetime import datetime
from fishing_assistant import window_target
from fishing_assistant.config import stop_shortcuts_label
from fishing_assistant.features.crafting.model import (
    CATEGORIES,
    CraftOptions,
    RECIPES,
    RECIPE_BY_KEY,
    MAX_QUEUE_CAPACITY,
    duration,
)


class CraftingPage(QScrollArea):
    def __init__(self, engine, parent=None):
        super().__init__(parent)
        from fishing_assistant.desktop.widgets import Card, ScrollSafeComboBox, ScrollSafeSpinBox
        self.engine = engine
        self._loading = True
        self._confirming = False
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        canvas = QWidget()
        canvas.setObjectName("pageCanvas")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 9, 0)
        layout.setSpacing(14)
        self.setWidget(canvas)

        def text(value, role="cardHint"):
            label = QLabel(value)
            label.setObjectName(role)
            label.setWordWrap(True)
            return label

        plan = Card()
        form = QGridLayout(plan)
        configure_card_layout(form)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        form.addWidget(text("制作计划", "cardTitle"), 0, 0, 1, 2)
        form.addWidget(text("请先打开游戏内对应的加工界面。"), 1, 0, 1, 2)
        self.category = ScrollSafeComboBox()
        for key, name in CATEGORIES.items():
            self.category.addItem(name, key)
        self.recipe = ScrollSafeComboBox()
        form.addWidget(text("加工分类", "fieldLabel"), 2, 0)
        form.addWidget(text("制作材料", "fieldLabel"), 2, 1)
        form.addWidget(self.category, 3, 0)
        form.addWidget(self.recipe, 3, 1)
        self.timing = text("", "helpStep")
        form.addWidget(self.timing, 4, 0, 1, 2)
        self.mode = ScrollSafeComboBox()
        self.mode.addItem("指定加工次数", "count")
        self.mode.addItem("用完材料为止", "exhaust")
        self.count = ScrollSafeSpinBox()
        self.count.setRange(1, 10000)
        self.count.setSuffix(" 次")
        self.count.setToolTip("一次代表向队列添加一个加工项目，不是产物件数。最后一轮只添加剩余次数。")
        self.count_label = text("加工次数", "fieldLabel")
        form.addWidget(text("停止条件", "fieldLabel"), 5, 0)
        form.addWidget(self.count_label, 5, 1)
        form.addWidget(self.mode, 6, 0)
        form.addWidget(self.count, 6, 1)
        self.rule = text("")
        form.addWidget(self.rule, 7, 0, 1, 2)
        self.capacity = ScrollSafeSpinBox()
        self.capacity.setRange(0, MAX_QUEUE_CAPACITY)
        self.capacity.setSpecialValueText("自动识别")
        self.capacity.setSuffix(" 格")
        self.capacity.setToolTip("默认按完整画面确认实际格数。也可手动填写；与画面不符会等待或停止，不盲目添加。")
        form.addWidget(text("队列容量", "fieldLabel"), 8, 0)
        form.addWidget(self.capacity, 8, 1)
        self._detected_capacity = 0
        layout.addWidget(plan)

        target_card = Card()
        target_card.setToolTip("自动制作固定使用 Windows Graphics Capture（WGC）捕获与窗口消息（PostMessage）输入，由 ok-script 提供；不受钓鱼窗口捕获选项影响。")
        target_layout = QVBoxLayout(target_card)
        configure_card_layout(target_layout)
        target_layout.addWidget(text("游戏窗口", "cardTitle"))
        target_layout.addWidget(text("后台运行，无需 F7；请勿最小化游戏。"))
        row = QHBoxLayout()
        self.target = ScrollSafeComboBox()
        self.target.setMinimumWidth(0)
        self.target.setPlaceholderText("请选择游戏窗口")
        self.refresh = QPushButton("刷新窗口")
        self.refresh.clicked.connect(self.refresh_windows)
        row.addWidget(self.target, 1)
        row.addWidget(self.refresh)
        target_layout.addLayout(row)
        self.start = QPushButton("开始自动制作")
        self.start.setObjectName("primaryButton")
        self.stop = QPushButton(f"停止（{stop_shortcuts_label(engine.config().stop_hotkey)}）")
        self.stop.setToolTip("停止助手操作，不会取消游戏中已加入的制作队列。")
        self.stop.setObjectName("dangerButton")
        self.start.clicked.connect(self.start_task)
        self.stop.clicked.connect(self.stop_task)
        actions = QHBoxLayout()
        actions.addWidget(self.start, 1)
        actions.addWidget(self.stop, 1)
        target_layout.addLayout(actions)
        self.availability = text("")
        target_layout.addWidget(self.availability)
        layout.addWidget(target_card)

        progress_card = Card()
        progress_layout = QVBoxLayout(progress_card)
        configure_card_layout(progress_layout)
        self.state = text("等待开始", "cardTitle")
        self.detail = text("")
        self.detail.setVisible(False)
        progress_layout.addWidget(self.state)
        progress_layout.addWidget(self.detail)
        self.slots_layout = QGridLayout()
        self.slots_layout.setSpacing(8)
        for column in range(4):
            self.slots_layout.setColumnStretch(column, 1)
        self.slot_labels = []
        self.capacity_status = text("队列尚未识别")
        progress_layout.addWidget(self.capacity_status)
        progress_layout.addLayout(self.slots_layout)
        self.totals = text("已添加 0 次 · 已领取 0 次")
        self.estimate = text("")
        self.estimate.setToolTip("仅预估本次添加项目的用时；领取以画面 100% 为准。开始前已有项目的剩余时间不作推断。")
        self.estimate.setVisible(False)
        progress_layout.addWidget(self.totals)
        progress_layout.addWidget(self.estimate)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(250)
        self.log.setMinimumHeight(100)
        self.log.setMaximumHeight(160)
        self.log.setPlaceholderText("制作日志")
        progress_layout.addWidget(self.log)
        layout.addWidget(progress_card)
        layout.addStretch(1)

        config = engine.config()
        selected = RECIPE_BY_KEY.get(config.crafting_recipe, RECIPES[0])
        self.category.setCurrentIndex(self.category.findData(selected.category))
        self.populate_recipes(selected.key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(config.crafting_mode)))
        self.count.setValue(config.crafting_count)
        self.capacity.setValue(config.crafting_queue_capacity)
        self._loading = False
        self.category.currentIndexChanged.connect(lambda: self.populate_recipes())
        self.recipe.currentIndexChanged.connect(self.save_plan)
        self.mode.currentIndexChanged.connect(self.save_plan)
        self.count.valueChanged.connect(self.save_plan)
        self.capacity.valueChanged.connect(self.save_plan)
        self.update_plan()
        self.target.currentIndexChanged.connect(self.sync_running)
        self.refresh_windows()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.sync_running)
        self.timer.start(500)
        self.sync_running()

    def set_theme(self, theme):
        day = theme == "day"
        self.setStyleSheet("")
        border, base, muted = ("#D9E5EA", "#F3F7FA", "#697C90") if day else ("#2B4258", "#132234", "#A5B6C8")
        green_bg, green_text = ("#E0F5EC", "#106E4D") if day else ("#163F34", "#8CF2C3")
        self.setStyleSheet(f'''
            QLabel#craftSlot {{ border: 1px solid {border}; border-radius: 9px; background: {base}; padding: 5px; }}
            QLabel#craftSlot[craftState="complete"] {{ background: {green_bg}; color: {green_text}; border-color: {green_text}; }}
            QPushButton#dangerButton:disabled {{ color: {muted}; background: {base}; border-color: {border}; }}
        ''')

    def populate_recipes(self, selected=None):
        self.recipe.blockSignals(True)
        self.recipe.clear()
        for recipe in RECIPES:
            if recipe.category == self.category.currentData():
                self.recipe.addItem(recipe.name, recipe.key)
        self.recipe.setCurrentIndex(max(0, self.recipe.findData(selected)))
        self.recipe.blockSignals(False)
        if hasattr(self, "mode"):
            self.save_plan()

    def update_plan(self):
        recipe = RECIPE_BY_KEY[self.recipe.currentData()]
        capacity = self.capacity.value() or self._detected_capacity
        batch_time = f" · 满队约 {duration(capacity*recipe.seconds)}" if capacity else ""
        self.timing.setText(f"单次 {duration(recipe.seconds)}{batch_time}")
        self.timing.setToolTip("按队列顺序加工；整队用时为实际格数乘以单次用时。")
        fixed = self.mode.currentData() == "count"
        self.count.setVisible(fixed)
        self.count_label.setVisible(fixed)
        if fixed:
            self.rule.setText(f"共 {self.count.value()} 次 · 预计 {duration(self.count.value()*recipe.seconds)}")
        else:
            self.rule.setText("材料不足时，领完已有产物后停止。")

    def save_plan(self, *_):
        if self._loading or self.recipe.currentData() is None:
            return
        self.update_plan()
        self.engine.update_config(crafting_recipe=self.recipe.currentData(), crafting_mode=self.mode.currentData(), crafting_count=self.count.value(),
                                  crafting_queue_capacity=self.capacity.value())

    def refresh_windows(self):
        if self.engine.is_monitoring() is True:
            return
        config = self.engine.config()
        selected = getattr(self, "_window_choices", {}).get(self.target.currentData())
        handle = selected.handle if selected else config.target_window_handle
        title = selected.title if selected else config.target_window_title
        try:
            windows = window_target.list_target_windows(include_minimized=True)
            self._window_discovery_error = ""
        except Exception as error:
            windows = []
            self._window_discovery_error = f"无法读取窗口列表：{error}"
        self._window_choices = {window.handle: window for window in windows}
        selected = window_target.select_target_window(windows, handle, title)
        with QSignalBlocker(self.target):
            self.target.clear()
            for window in windows:
                self.target.addItem(window.display_label, window.handle)
            self.target.setCurrentIndex(self.target.findData(selected.handle) if selected else -1)
        self.sync_running()

    def sync_running(self):
        busy = self.engine.is_monitoring()
        crafting = self.engine.is_crafting()
        paused = self.engine.is_paused() is True
        target = getattr(self, "_window_choices", {}).get(self.target.currentData())
        minimized = target is not None and target.minimized
        for widget in (self.category, self.recipe, self.mode, self.count, self.capacity, self.target, self.refresh):
            widget.setEnabled(not busy)
        self.start.setEnabled(not busy and self.target.currentData() is not None and not minimized)
        if self._confirming:
            self.start.setEnabled(False)
        self.stop.setEnabled(crafting)
        if crafting:
            availability = "已暂停 · 可从悬浮栏继续" if paused else ""
        elif busy:
            availability = "请先停止钓鱼或背包整理，再开始制作。"
        elif getattr(self, "_window_discovery_error", ""):
            availability = self._window_discovery_error
        elif minimized:
            availability = "游戏已最小化，请恢复窗口后刷新。"
        else:
            availability = "请选择游戏窗口；未找到时点击“刷新窗口”。" if target is None else ""
        self.availability.setText(availability)
        self.availability.setVisible(bool(self.availability.text()))

    def start_task(self):
        if self._confirming or self.engine.is_monitoring():
            return
        handle = self.target.currentData()
        if handle is None:
            self._show_start_failure("请选择游戏窗口；未找到时请打开游戏并刷新窗口列表。")
            return
        target = getattr(self, "_window_choices", {}).get(handle)
        if target is not None and target.minimized:
            self._show_start_failure("游戏已最小化，请恢复窗口后刷新。")
            return
        options = CraftOptions(self.recipe.currentData(), self.mode.currentData(), self.count.value(), self.capacity.value())
        try:
            options.validate()
        except ValueError as error:
            self._show_start_failure(str(error))
            return
        self._confirming = True
        self.sync_running()
        try:
            if not self._confirm_start(options):
                return
            if not self.engine.start_crafting(options, int(handle)):
                self._show_start_failure("任务未启动。请检查目标窗口是否仍存在、其他任务是否已停止；具体原因见控制台日志。")
                return
            self._detected_capacity = 0
            self._resize_slot_labels(0)
            self.state.setText("正在核对队列")
            self.detail.setText("正在识别加工界面…")
            self.detail.setVisible(True)
            self.capacity_status.setText("正在识别队列容量…")
            self.totals.setText("本次已添加 0 次 · 已领取 0 次")
            self.estimate.clear()
            self.estimate.setVisible(False)
            self.update_plan()
        finally:
            self._confirming = False
            self.sync_running()

    def _show_start_failure(self, message):
        self.state.setText("制作未启动")
        self.detail.setText(message)
        self.detail.setVisible(True)
        self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  制作未启动：{message}")
        self.sync_running()

    def _confirm_start(self, options):
        name = RECIPE_BY_KEY[options.recipe].name
        dialog = QMessageBox(QMessageBox.Icon.Question, "开始自动制作？",
            f"材料：{name}\n计划：" + (f"加工 {options.count} 次" if options.mode == "count" else "用完材料为止") +
            "\n队列容量：" + (f"核对 {options.queue_capacity} 格" if options.queue_capacity else "自动识别"),
            parent=self)
        dialog.setOption(QMessageBox.Option.DontUseNativeDialog, True)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setInformativeText("请打开对应加工界面的“全部”列表，保持所有队列格可见。\n\n开始后会消耗所选材料；已有队列会等待并领取，不计入本次次数。")
        information = dialog.findChild(QLabel, "qt_msgbox_informativelabel")
        if information is not None:
            information.setWordWrap(True)
            information.setMinimumWidth(300)
            information.setMaximumWidth(390)
        confirm = QPushButton("开始制作")
        confirm.setObjectName("primaryButton")
        dialog.addButton(confirm, QMessageBox.ButtonRole.AcceptRole)
        cancel = dialog.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        dialog.setDefaultButton(cancel)
        try:
            dialog.exec()
            return dialog.clickedButton() is confirm
        finally:
            dialog.deleteLater()

    def stop_task(self):
        if self.engine.is_crafting():
            self.engine.set_monitoring(False)
        self.sync_running()

    def update_progress(self, progress, log=False):
        names = {"inspect": "核对队列 / 等待加工", "await_dialog": "打开材料详情", "await_add": "确认添加结果",
                 "await_close": "返回加工界面", "await_result": "领取全部产物", "await_return": "确认领取", "done": "制作已结束", "error": "制作已停止"}
        self.state.setText(names.get(progress.phase, "自动制作"))
        self.detail.setText(progress.message)
        self.detail.setVisible(bool(progress.message))
        self._resize_slot_labels(len(progress.slots))
        if progress.slots:
            self._detected_capacity = len(progress.slots)
            unclear = progress.slots.count("unknown")
            self.capacity_status.setText(f"当前队列 {len(progress.slots)} 格" + (f" · {unclear} 格待确认" if unclear else " · 全部槽位已识别"))
            self.update_plan()
        slot_names = {"empty": "空槽", "busy": "加工中 / 排队", "complete": "100% · 完成", "unknown": "待识别"}
        for index, (label, state) in enumerate(zip(self.slot_labels, progress.slots), 1):
            label.setText(f"第 {index} 格\n{slot_names.get(state, '待识别')}")
            if label.property("craftState") != state:
                label.setProperty("craftState", state)
                label.style().unpolish(label)
                label.style().polish(label)
        self.totals.setText(f"本次已添加 {progress.submitted} 次 · 已领取 {progress.collected} 次")
        self.estimate.setText(f"预计剩余 {duration(progress.estimate_seconds)}" if progress.estimate_seconds > 0 else "")
        self.estimate.setVisible(bool(self.estimate.text()))
        if log:
            self.log.appendPlainText(f"{datetime.now():%H:%M:%S}  {progress.message}")
        self.sync_running()

    def _resize_slot_labels(self, count):
        """每行四张等宽卡片，1、5 或更多格都按实际数量增减，不留旧状态。"""
        while len(self.slot_labels) > count:
            label = self.slot_labels.pop()
            self.slots_layout.removeWidget(label)
            label.deleteLater()
        while len(self.slot_labels) < count:
            index = len(self.slot_labels)
            label = QLabel(f"第 {index+1} 格\n待识别")
            label.setWordWrap(True)
            label.setObjectName("craftSlot")
            label.setProperty("craftState", "unknown")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setMinimumHeight(58)
            self.slots_layout.addWidget(label, index//4, index%4)
            self.slot_labels.append(label)
