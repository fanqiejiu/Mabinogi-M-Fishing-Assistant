"""Fishing session history table and aggregate statistics."""
from __future__ import annotations

from datetime import datetime
import sqlite3

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fishing_assistant.desktop.design import configure_card_layout
from fishing_assistant.desktop.widgets import Card, MetricCard
from fishing_assistant.features.fishing_history.store import FishingHistoryRecord


class FishingHistoryPage(QScrollArea):
    """Browse recent automatic-fishing sessions and analyze cumulative results."""

    def __init__(self, engine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.engine = engine
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        canvas = QWidget()
        canvas.setObjectName("pageCanvas")
        layout = QVBoxLayout(canvas)
        layout.setContentsMargins(0, 0, 9, 0)
        layout.setSpacing(14)
        self.setWidget(canvas)

        summary_card = Card()
        summary_layout = QVBoxLayout(summary_card)
        configure_card_layout(summary_layout)
        heading = QHBoxLayout()
        title = QLabel("累计统计")
        title.setObjectName("cardTitle")
        heading.addWidget(title)
        heading.addStretch(1)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh)
        heading.addWidget(self.refresh_button)
        summary_layout.addLayout(heading)
        summary_layout.addWidget(
            self._hint(
                "每次成功启动自动钓鱼生成一条会话；暂停时间计入自然会话时长。"
                "汇总覆盖所有已保存会话，列表显示最近 100 条。"
            )
        )

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)
        self.session_metric = MetricCard("会话数", "0")
        self.round_metric = MetricCard("已分类轮次", "0")
        self.catch_metric = MetricCard("上鱼成功", "0")
        self.ordinary_metric = MetricCard("普通成功", "0")
        self.failure_metric = MetricCard("失败", "0")
        self.success_rate_metric = MetricCard("成功占比", "0%")
        self.total_duration_metric = MetricCard("总钓鱼时间", "0 秒")
        for index, metric in enumerate(
            (
                self.session_metric,
                self.round_metric,
                self.catch_metric,
                self.ordinary_metric,
                self.failure_metric,
                self.success_rate_metric,
                self.total_duration_metric,
            )
        ):
            metrics.addWidget(metric, index // 4, index % 4)
        summary_layout.addLayout(metrics)
        layout.addWidget(summary_card)

        history_card = Card()
        history_layout = QVBoxLayout(history_card)
        configure_card_layout(history_layout)
        history_layout.addWidget(self._heading("最近会话"))
        self.error_label = self._hint("")
        self.error_label.setObjectName("safetyWarning")
        self.error_label.hide()
        history_layout.addWidget(self.error_label)
        self.table = QTableWidget(0, 7)
        self.table.setObjectName("fishingHistoryTable")
        self.table.setHorizontalHeaderLabels(
            ("开始时间", "结束时间", "上鱼成功", "普通成功", "失败", "时长", "状态")
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumWidth(0)
        self.table.verticalHeader().setObjectName("fishingHistoryRowHeader")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((155, 155, 82, 82, 70, 100, 96)):
            self.table.setColumnWidth(column, width)
        header.setStretchLastSection(True)
        self.table.setMinimumHeight(300)
        history_layout.addWidget(self.table)
        layout.addWidget(history_card)
        layout.addStretch(1)
        self._theme = "night"
        self.refresh()

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardTitle")
        return label

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardHint")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _format_timestamp(value: str | None) -> str:
        if value is None:
            return "进行中"
        return datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_duration(record: FishingHistoryRecord) -> str:
        if record.ended_at is None:
            return "进行中"
        started = datetime.fromisoformat(record.started_at)
        ended = datetime.fromisoformat(record.ended_at)
        seconds = max(0, int((ended - started).total_seconds()))
        minutes, remaining = divmod(seconds, 60)
        if minutes:
            return f"{minutes} 分 {remaining} 秒"
        return f"{remaining} 秒"

    @staticmethod
    def _format_status(record: FishingHistoryRecord) -> str:
        if record.status == "interrupted":
            return "异常中断"
        if record.status == "running":
            return "进行中"
        reasons = {
            "stopped": "手动停止",
            "application_closed": "关闭程序",
            "automatic_error": "自动制作异常",
            "recognition_error": "识别重试耗尽",
            "monitor_start_error": "监测启动异常",
            "blocking_game_prompt": "游戏提示停止",
            "recovery_limit": "恢复次数耗尽",
            "inventory_test_completed": "背包测试结束",
            "inventory_error": "背包操作异常",
        }
        return reasons.get(record.end_reason, "已结束")

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        catch_color, failure_color = (
            (QColor("#75E4BE"), QColor("#FFB7A5"))
            if theme == "night"
            else (QColor("#107450"), QColor("#A23825"))
        )
        for row in range(self.table.rowCount()):
            for column, color in ((2, catch_color), (3, catch_color), (4, failure_color)):
                item = self.table.item(row, column)
                if item is not None:
                    item.setForeground(color)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

    def refresh(self) -> None:
        try:
            summary = self.engine.fishing_history_summary()
            records = self.engine.fishing_history_sessions(100)
        except (OSError, sqlite3.Error, RuntimeError) as error:
            self.error_label.setText(f"读取钓鱼历史失败：{error}")
            self.error_label.show()
            return

        self.error_label.hide()
        self.session_metric.value_label.setText(str(summary.session_count))
        self.round_metric.value_label.setText(str(summary.total_rounds))
        self.catch_metric.value_label.setText(str(summary.catch_count))
        self.ordinary_metric.value_label.setText(str(summary.ordinary_count))
        self.failure_metric.value_label.setText(str(summary.failure_count))
        self.success_rate_metric.value_label.setText(
            f"{summary.success_rate:.1%}"
        )
        total_seconds = int(summary.total_duration_seconds)
        total_minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(total_minutes, 60)
        duration = (
            f"{hours} 小时 {minutes} 分"
            if hours
            else f"{minutes} 分"
            if minutes
            else f"{seconds} 秒"
        )
        self.total_duration_metric.value_label.setText(duration)

        self.table.setRowCount(len(records))
        for row_index, record in enumerate(records):
            values = (
                self._format_timestamp(record.started_at),
                self._format_timestamp(record.ended_at),
                str(record.catch_count),
                str(record.ordinary_count),
                str(record.failure_count),
                self._format_duration(record),
                self._format_status(record),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (2, 3, 4):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row_index, column, item)
        self.set_theme(self._theme)
