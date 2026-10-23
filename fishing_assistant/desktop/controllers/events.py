"""引擎事件到状态栏、日志和语音的展示映射"""
from __future__ import annotations
from fishing_assistant.desktop.terminology import ICON_MATCH_SCORE_LABEL

from datetime import datetime
from fishing_assistant.engine import EngineEvent, EventKind, FishingEngine, IconState
from fishing_assistant.voice_alerts import F8_STOP_CUE, cue_for_engine_event
from fishing_assistant.desktop.widgets import update_status_label


class EngineEventsMixin:
    """引擎事件到状态栏、日志和语音的展示映射；由 MainWindow 组装，不单独实例化。"""

    def _calibrate(self) -> None:
        self.calibration_summary.setText("将鼠标停在钓鱼按钮中心，按 F7 校准。")
        self._append_log("校准说明已显示：请把鼠标停在钓鱼按钮中心后按 F7；不要点击助手窗口来记录坐标。", EventKind.INFO)

    def _toggle_monitoring(self) -> None:
        self.engine.set_monitoring(not self.engine.is_monitoring())

    def _refresh_calibration_summary(self) -> None:
        config = self.engine.config()
        self._sync_floating_calibration_state()
        if config.capture_mode == "window":
            if config.target_button_offset is None:
                self.calibration_summary.setText("选择游戏窗口后，将鼠标停在钓鱼按钮中心，按 F7。")
                self._set_runtime_state("等待校准")
                return
            offset_x, offset_y = config.target_button_offset
            self.calibration_summary.setText(
                f"已校准后台目标：{config.target_window_title or '未命名窗口'}  ·  窗口内 ({offset_x}, {offset_y})"
            )
        else:
            if config.button_center is None:
                self.calibration_summary.setText("将鼠标停在钓鱼按钮中心，按 F7 校准。")
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
        self._sync_floating_task_controls()
        if event.kind == EventKind.PAUSE:
            if not self.engine.is_monitoring():
                return  # 停止后才到达的暂停/继续通知不覆盖“已停止”。
            paused = self.engine.is_paused() is True
            text = "已暂停" if paused else "重新识别中"
            self._set_runtime_state(text, "warning" if paused else "running")
            self._set_status("warning" if paused else "running", "● " + text)
            self.runtime_title.setText(text)
            self.runtime_detail.setText(event.message)
            if self.engine.is_crafting() is True:
                self.crafting_page.state.setText("制作已暂停" if paused else "重新核对队列")
                self.crafting_page.detail.setText(event.message)
            if paused:
                self.voice_player.clear_pending()
            self._append_log(event.message, EventKind.INFO)
            return
        if self.engine.is_paused() is True and event.kind in {EventKind.METRIC, EventKind.STATE, EventKind.CRAFTING}:
            return
        if event.kind == EventKind.CRAFTING:
            progress = event.crafting
            if progress is None or progress.generation != self.engine._interrupt_generation:
                return
            self._floating_crafting_session = True
            self._sync_floating_status_visibility()
            self.crafting_page.update_progress(progress, event.crafting_log)
            failed = progress.phase == "error"
            state = "warning" if failed else "running" if progress.running else "idle"
            phases = {"await_dialog": "打开材料", "await_add": "确认添加", "await_close": "返回队列",
                      "await_result": "领取产物", "await_return": "确认领取"}
            inspection = "核对队列" if not progress.slots or "unknown" in progress.slots else "等待加工"
            caption = "制作异常" if failed else phases.get(progress.phase, inspection) if progress.running else "制作已停止"
            self.runtime_title.setText("自动制作异常" if failed else "自动制作中" if progress.running else "自动制作已停止")
            self.runtime_detail.setText(progress.message)
            self._set_runtime_state(caption, state)
            self.floating_status_bar.runtime_label.setToolTip(progress.message)
            self._set_status(state, "● " + ("制作异常" if failed else "自动制作中" if progress.running else "制作已停止"))
            self.start_button.setText("停止当前任务" if progress.running else "开始监测")
            button_role = "dangerButton" if progress.running else "primaryButton"
            if self.start_button.objectName() != button_role:
                self.start_button.setObjectName(button_role)
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
            if event.crafting_log:
                self._append_log(progress.message, EventKind.WARNING if progress.phase == "error" else EventKind.INFO)
            return
        if event.kind == EventKind.DIAGNOSTIC:
            saving = event.snapshot_state == "saving"
            self.snapshot_button.setEnabled(not saving)
            self.snapshot_button.setText("正在保存…" if saving else "保存现场（F9）")
            if saving:
                self.view_snapshot_button.setEnabled(False)
                self.snapshot_status.setText("正在保存识别现场…F8 和设置的停止快捷键仍可使用。")
            else:
                self._last_snapshot_path = event.debug_image
                self._last_snapshot_bundle = event.diagnostic_path
                self.view_snapshot_button.setEnabled(event.debug_image is not None)
                self.snapshot_status.setText(
                    "截图和诊断包已保存，仅保存在本机。"
                    if event.snapshot_state == "saved" else event.message
                )
            self.snapshot_status.setToolTip(event.message)
            self._append_log(
                event.message,
                EventKind.WARNING if event.snapshot_state in {"failed", "partial"} else EventKind.INFO,
            )
            return
        # Qt 信号可能晚于 F8 停止到达，不让旧指标把状态栏改回“运行中”。
        if event.kind == EventKind.METRIC and not self.engine.is_monitoring():
            return
        if event.kind == EventKind.STATE and event.monitoring != self.engine.is_monitoring():
            return
        if event.kind == EventKind.STATE:
            self._sync_floating_status_visibility()
        if hasattr(self, "remote_panel"):
            self.remote_panel.reporter.observe(event)
        voice_cue = cue_for_engine_event(
            event.kind,
            event.message,
            event.monitoring,
        )
        if voice_cue == F8_STOP_CUE:
            self.voice_player.clear_pending()
        if voice_cue is not None:
            self.voice_player.play(voice_cue)

        if event.kind == EventKind.METRIC:
            if event.recognition_source in {"ok_feature", "v2_signature", "compass_pixel"}:
                confidence = max(0.0, min(1.0, event.recognition_confidence))
                caption = (
                    "指南针中心黑点"
                    if event.recognition_source == "compass_pixel"
                    else ICON_MATCH_SCORE_LABEL
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
                cleaning_inventory = event.message.startswith(
                    ("自动清理背包", "背包清理调试")
                )
                self.runtime_detail.setText(
                    event.message
                    if cleaning_inventory
                    else (
                        "正在识别目标窗口中的钓鱼图标。"
                        if self.engine.config().capture_mode == "window"
                        else "正在识别右下角圆形按钮。"
                    )
                )
                self.start_button.setText("停止监测")
                self.start_button.setObjectName("dangerButton")
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
                self._set_status("running", "●  监测运行中")
                self._set_runtime_state(
                    "清理背包" if cleaning_inventory else "识别中",
                    "running",
                )
            else:
                self.runtime_title.setText("已停止")
                self.runtime_detail.setText(event.message or "已停止，不再发送按键。")
                self.start_button.setText("开始监测")
                self.start_button.setObjectName("primaryButton")
                self.start_button.style().unpolish(self.start_button)
                self.start_button.style().polish(self.start_button)
                self._refresh_calibration_summary()
                self._set_runtime_state("已停止")
        elif event.kind == EventKind.WARNING:
            self._set_status("warning", "●  需要注意")
            self._set_runtime_state("需要处理", "warning")
            self.runtime_detail.setText(event.message)
        elif event.kind == EventKind.ERROR:
            if self.engine.is_monitoring():
                # 保存快照等辅助操作报错不等于钓鱼线程已经停止。
                self._set_status("warning", "●  运行中 · 需要注意")
                self.runtime_detail.setText(event.message)
                return
            self._set_status("warning", "●  识别已停止")
            self._set_runtime_state("已停止", "warning")
            self.runtime_detail.setText(event.message)
            self.runtime_title.setText("已停止")
            self.start_button.setText("开始监测")
            self.start_button.setObjectName("primaryButton")
            self.start_button.style().unpolish(self.start_button)
            self.start_button.style().polish(self.start_button)
        elif event.kind == EventKind.SUCCESS:
            self.runtime_detail.setText(event.message)
            if event.debug_image is not None:
                self.snapshot_status.setText("区域快照与识别诊断已保存")
            self._refresh_calibration_summary()
        if hasattr(self, "test_inventory_cleanup_button"):
            self._sync_inventory_cleanup_debug_controls()

    def _set_runtime_state(self, text: str, state: str = "idle") -> None:
        update_status_label(self.runtime_state_chip, state, f"状态 · {text}")
        self.floating_status_bar.set_runtime(text, state)

    def _set_status(self, state: str, text: str) -> None:
        update_status_label(self.status_chip, state, text)

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
