"""钓鱼设置标签页。"""
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .base import BasePageMixin
from ..widget.card import Card
from ..widget.controls import ScrollSafeComboBox, ScrollSafeSlider

class FishingPageMixin(BasePageMixin):
    def _build_detection_page(self) -> QScrollArea:
        scroll, layout = BasePageMixin._new_page_canvas()

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
        timing_formula = QLabel(
            "兜底计算：记录跑鱼总时长 T，提前量取 T × 10%（限制为 1.0–2.0 秒），"
            "下一轮在 max(1.0 秒, T − 提前量) 时收杆。正常识别到反弹时仍立即收杆。"
        )
        timing_formula.setObjectName("helper")
        timing_formula.setWordWrap(True)
        timing_layout.addWidget(timing_formula)
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
                "指南针出现时按所选方式移动；钓鱼图标恢复后自动按 Space。",
            )
        )
        self.auto_resume_check = QCheckBox(
            "收鱼后自动按 Space 继续钓鱼"
        )
        self.auto_recover_check = QCheckBox(
            "检测到指南针状态时自动移动恢复"
        )
        recovery_layout.addWidget(self.auto_resume_check)
        recovery_layout.addWidget(self.auto_recover_check)

        self.recovery_mode_combo = ScrollSafeComboBox()
        self.recovery_mode_combo.addItem("W → S 往返恢复（默认推荐）", "ws")
        self.recovery_mode_combo.addItem("仅按 W 向前恢复", "w_only")
        recovery_layout.addWidget(
            self._form_label(
                "恢复方式",
                "W/S 适合原地刷新；仅 W 适合需要持续向岸边方向移动的情况。",
            )
        )
        recovery_layout.addWidget(self.recovery_mode_combo)

        self.recovery_hold_spin = self._spin_box(80, 600, 180, " ms")
        self.recovery_cooldown_spin = self._spin_box(
            1000, 10000, 4500, " ms"
        )
        self.recovery_attempt_limit_spin = self._spin_box(1, 20, 5, " 次")
        self.recovery_forward_interval_spin = self._spin_box(0, 20, 2, " 次")
        self.recovery_forward_taps_spin = self._spin_box(1, 10, 1, " 次")
        self.recovery_w_only_count_spin = self._spin_box(1, 20, 1, " 次")
        self.recovery_w_only_hold_spin = self._double_spin_box(
            0.1, 5.0, 0.5, " 秒"
        )

        def recovery_control_grid(
            controls: list[tuple[str, str, QWidget]],
        ) -> QWidget:
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(8)
            for index, (label, hint, control) in enumerate(controls):
                row = (index // 2) * 2
                column = index % 2
                grid.addWidget(self._form_label(label, hint), row, column)
                grid.addWidget(control, row + 1, column)
                grid.setColumnStretch(column, 1)
            return container

        ws_panel = option_panel(
            "W → S 模式参数",
            "先短按 W 再短按 S；连续失败时可按周期额外补按 W。",
        )
        ws_panel.layout().addWidget(
            recovery_control_grid(
                [
                    (
                        "W / S 按住时间",
                        "每个方向的短按时长",
                        self.recovery_hold_spin,
                    ),
                    (
                        "向前补偿周期",
                        "每累计几次 W→S 后触发；0 为关闭",
                        self.recovery_forward_interval_spin,
                    ),
                    (
                        "补按 W 次数",
                        "触发时额外连续短按 W",
                        self.recovery_forward_taps_spin,
                    ),
                ]
            )
        )
        w_only_panel = option_panel(
            "仅 W 模式参数",
            "每轮只发送 W，不发送 S；使用前必须将游戏镜头改为手动镜头。",
        )
        w_only_panel.layout().addWidget(
            recovery_control_grid(
                [
                    (
                        "连续按 W 次数",
                        "每轮移动恢复执行几次 W",
                        self.recovery_w_only_count_spin,
                    ),
                    (
                        "每次长按时间",
                        "单次 W 持续 0.1–5.0 秒",
                        self.recovery_w_only_hold_spin,
                    ),
                ]
            )
        )
        self.recovery_mode_stack = QStackedWidget()
        self.recovery_mode_stack.addWidget(ws_panel)
        self.recovery_mode_stack.addWidget(w_only_panel)
        recovery_layout.addWidget(self.recovery_mode_stack)

        recovery_layout.addWidget(
            self._form_label("通用恢复设置", "两种恢复方式共用冷却和失败上限。")
        )
        recovery_layout.addWidget(
            recovery_control_grid(
                [
                    (
                        "恢复冷却",
                        "避免持续失效时反复移动",
                        self.recovery_cooldown_spin,
                    ),
                    (
                        "恢复上限",
                        "连续失败达到上限后停止监测",
                        self.recovery_attempt_limit_spin,
                    ),
                ]
            )
        )
        layout.addWidget(recovery_card)

        cleanup_card, cleanup_safety_card = self._build_inventory_cleanup_cards()
        layout.addWidget(cleanup_card)
        layout.addWidget(cleanup_safety_card)

        layout.addStretch(1)
        return scroll

    def _build_inventory_cleanup_cards(self) -> tuple[Card, Card]:
        cleanup_card = Card()
        cleanup_layout = QVBoxLayout(cleanup_card)
        cleanup_layout.setContentsMargins(24, 22, 24, 22)
        cleanup_layout.setSpacing(12)
        cleanup_layout.addLayout(
            self._card_heading(
                "背包清理（实验性）",
                "背包满时使用四类简单整理，完成后退出背包并恢复钓鱼。",
            )
        )
        self.inventory_cleanup_check = QCheckBox(
            "检测到背包已满后自动清理并继续钓鱼"
        )
        self.inventory_cleanup_check.setChecked(False)
        self.inventory_cleanup_check.setToolTip(
            "实验性不可逆操作；默认关闭，启用前必须确认风险"
        )
        cleanup_layout.addWidget(self.inventory_cleanup_check)

        warning = QLabel(
            "此功能可能永久分解或出售物品，也存在识别误判后误用“大胆整理”的风险。"
            "请只在能够承担该风险时启用。"
        )
        warning.setObjectName("cardHint")
        warning.setWordWrap(True)
        cleanup_layout.addWidget(warning)

        safety_card = Card()
        safety_layout = QVBoxLayout(safety_card)
        safety_layout.setContentsMargins(24, 22, 24, 22)
        safety_layout.setSpacing(9)
        safety_layout.addLayout(
            self._card_heading(
                "执行前安全检查",
                "以下条件有一项不明确，清理流程就会停止。",
            )
        )
        for text in (
            "1. 先识别背包页和简单整理页，不按固定坐标盲点。",
            "2. 关闭“大胆整理”后连续确认 3 帧。",
            "3. 选择四类简单整理项目，再连续确认 3 帧。",
            "4. 整理对象页、完成页和“已整理背包”提示逐页确认。",
        ):
            label = QLabel(text)
            label.setObjectName("helper")
            label.setWordWrap(True)
            safety_layout.addWidget(label)
        return cleanup_card, safety_card

