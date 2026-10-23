"""校准、启停和钓鱼／制作／背包测试互斥入口"""
from __future__ import annotations

import pyautogui
import time
import sqlite3
from fishing_assistant import window_target
from fishing_assistant.automation.models import EventKind, FishingResult


class TaskControlMixin:
    """校准、启停和钓鱼／制作／背包测试互斥入口；由 FishingEngine 组装，不单独实例化。"""

    def calibrate_from_cursor(self) -> tuple[int, int]:
        if self.is_crafting():
            self._emit(EventKind.INFO, "自动制作期间无需 F7 校准；请先停止制作再校准钓鱼。")
            return tuple(pyautogui.position())
        x, y = pyautogui.position()
        config = self.config()
        if config.capture_mode == "window":
            try:
                target = self._resolve_target_window(config)
            except RuntimeError as error:
                self._emit(EventKind.WARNING, f"后台模式校准失败：{error}")
                return x, y
            if not target.contains(x, y):
                self._emit(
                    EventKind.WARNING,
                    "鼠标不在选定的目标窗口内，请先切到目标窗口再校准。",
                )
                return x, y
            offset = (x - target.left, y - target.top)
            self.update_config(
                button_center=(x, y),
                target_window_handle=target.handle,
                target_window_title=target.title,
                target_button_offset=offset,
            )
            message = (
                f"F7 已校准目标窗口“{target.title}”内按钮：({offset[0]}, {offset[1]})；"
                "已直接记录，鼠标位置未移动。"
            )
        else:
            self.update_config(button_center=(x, y))
            message = f"F7 已校准钓鱼按钮中心：({x}, {y})；已直接记录，鼠标位置未移动。"
        self._reset_detection()
        if self._enabled.is_set():
            self._startup_probe_active = True
            self._schedule_recast(
                time.monotonic(), self.config(), "重新校准完成"
            )
        self._emit(EventKind.SUCCESS, message)
        return x, y

    def set_monitoring(self, enabled: bool) -> bool:
        # 启动互斥，但停止不等待启动锁，F8/Esc 可立即撤销旧动作资格。
        if enabled:
            with self._config_lock:
                return self._set_monitoring(enabled)
        return self._set_monitoring(enabled)

    def _set_monitoring(self, enabled: bool) -> bool:
        if not enabled:
            # 先撤销送键资格，再重置识别数据，避免旧帧趁重置期间继续动作。
            self._interrupt_generation += 1
            self._enabled.clear()
            self._finish_fishing_session("stopped")
            self._paused.clear()
            self._cleanup_test_requested.clear()
            request = self._craft_request
            self._craft_request = None
            if request is not None:
                session, _target = request
                session.stop("自动制作已停止；已加入的游戏队列不会被取消。")
                self._emit_crafting(session.progress(time.monotonic(), self._interrupt_generation), log=True)
            self._reset_detection()
            self._emit(EventKind.STATE, "监测已暂停，不会发送按键。", monitoring=False)
            return True
        if self._enabled.is_set() or self._shutdown.is_set():
            return self._enabled.is_set() and not self._shutdown.is_set()
        generation = self._interrupt_generation
        config = self.config()
        if enabled:
            if config.capture_mode == "window":
                if config.target_button_offset is None:
                    self._emit(EventKind.WARNING, "请先选择目标窗口并在窗口内完成校准。")
                    return False
                try:
                    self._resolve_target_window(config)
                except RuntimeError as error:
                    self._emit(EventKind.WARNING, f"无法启动后台模式：{error}")
                    return False
            elif config.button_center is None:
                self._emit(EventKind.WARNING, "请先把鼠标停在圆形按钮中心后按 F7 校准。")
                return False
        self._reset_detection()
        if enabled:
            self._cleanup_test_requested.clear()
            self._startup_probe_active = True
            self._unrecognized_since = None
            self._last_diag_snapshot_at = None
            self._diag_snapshot_count = 0
            self._prepare_stamina_view(config)
            if generation != self._interrupt_generation or self._shutdown.is_set():
                return False
            if config.capture_mode == "window":
                try:
                    target = self._resolve_target_window(config)
                    # hover 阶段窗口也可能刚好消失，必须同在保护范围内。
                    self._maintain_background_hover(target, config, force=True)
                except RuntimeError as error:
                    self._startup_probe_active = False
                    self._emit(EventKind.WARNING, f"无法启动后台模式：{error}")
                    return False
                self._emit(
                    EventKind.INFO,
                    f"后台虚拟悬停已锁定至窗口内 {config.target_button_offset}；真实鼠标可自由移动。",
                    monitoring=True,
                )
            if generation != self._interrupt_generation or self._shutdown.is_set():
                return False
            self._enabled.set()
            try:
                self._start_fishing_session()
            except (OSError, sqlite3.Error) as error:
                self._enabled.clear()
                self._emit(
                    EventKind.ERROR,
                    f"无法保存本次钓鱼历史记录，监测未启动：{error}",
                    monitoring=False,
                )
                return False
            self._schedule_recast(time.monotonic(), config, "监测启动")
            self._emit(EventKind.INFO, self._monitoring_details(config), monitoring=True)
            self._emit_environment_warnings(config)
            if config.capture_mode == "window" and config.window_backend == "ok":
                self._emit(EventKind.INFO, "WGC 正在等待首帧，画面到达后自动开始识别。", monitoring=True)
            message = (
                "OK 指定窗口模式已启动；临时错误会按设置重试，达到上限后暂停。"
                if config.capture_mode == "window"
                else "监测已启动，请把游戏保持在前台。"
            )
            self._emit(EventKind.STATE, message, monitoring=True)
        return True

    def _start_fishing_session(self) -> None:
        self._fishing_history_id = self._fishing_history.start_session()
        self._fishing_session_id += 1
        self._successful_fishing_count = 0
        self._ordinary_fishing_count = 0
        self._failed_fishing_count = 0
        self._fishing_session_active = True
        self._reset_fishing_round_tracking()
        self._emit_fishing_session_stats()

    def _record_fishing_session_result(self, result: FishingResult) -> None:
        if not self._fishing_session_active or not self._enabled.is_set():
            return
        generation = getattr(self._work_context, "generation", None)
        if generation is not None and not self._operation_active(generation):
            return
        if self._fishing_history_id is not None:
            self._fishing_history.record_result(self._fishing_history_id, result)
        if result == FishingResult.CATCH:
            self._successful_fishing_count += 1
        elif result == FishingResult.ORDINARY:
            self._ordinary_fishing_count += 1
        else:
            self._failed_fishing_count += 1
        self._emit_fishing_session_stats()

    def _finish_fishing_session(self, end_reason: str) -> None:
        if not self._fishing_session_active:
            return
        session_id = self._fishing_history_id
        if session_id is not None:
            try:
                self._fishing_history.finish_session(session_id, end_reason)
            except (OSError, sqlite3.Error, RuntimeError) as error:
                self._emit(
                    EventKind.ERROR,
                    f"本次钓鱼历史未能正常结束保存；下次启动会标记为中断：{error}",
                    monitoring=False,
                )
        self._fishing_session_active = False
        self._fishing_history_id = None
        self._emit_fishing_session_stats()

    def _emit_fishing_session_stats(self) -> None:
        self._emit(
            EventKind.FISHING_SESSION_STATS,
            "本次自动钓鱼记录已更新。",
            fishing_session_id=self._fishing_session_id,
            successful_fishing_count=self._successful_fishing_count,
            ordinary_fishing_count=self._ordinary_fishing_count,
            failed_fishing_count=self._failed_fishing_count,
        )

    def _reset_fishing_round_tracking(self) -> None:
        self._fish_round_had_stamina = False
        self._fish_round_depleted = False
        self._fish_round_rebounded = False
        self._fish_round_full_recovered = False
        self._fish_round_initial_width = 0
        self._fish_round_collect_pressed = False
        self._fish_round_last_stamina_at = 0.0

    def toggle_monitoring(self) -> None:
        # F8 始终保留启停语义；悬浮栏“继续”不等于重新启动其他任务。
        self.set_monitoring(not self._enabled.is_set())

    def is_monitoring(self) -> bool:
        return self._enabled.is_set()

    def is_crafting(self) -> bool:
        return self._craft_request is not None and self._enabled.is_set()

    def _emit_crafting(self, progress, *, log=False) -> None:
        self._emit(EventKind.CRAFTING, progress.message, monitoring=progress.running,
                   crafting=progress, crafting_log=log)

    def start_crafting(self, options, handle: int) -> bool:
        with self._config_lock:
            return self._start_crafting(options, handle)

    def _start_crafting(self, options, handle: int) -> bool:
        from fishing_assistant.features.crafting.model import CraftSession
        if self._debug_capture_lock.locked():
            self._emit(EventKind.WARNING, "正在保存 F9 识别现场，请等待完成后再开始制作。")
            return False
        if self._enabled.is_set() or self._shutdown.is_set() or self._craft_request is not None:
            self._emit(EventKind.WARNING, "请先停止当前钓鱼、整理或制作任务，再启动自动制作。")
            return False
        generation = self._interrupt_generation
        try:
            session = CraftSession(options, time.monotonic())
            target = window_target.get_window_info(handle)
            if target is None:
                raise RuntimeError("请选择已打开加工界面的游戏窗口。")
            if not window_target.OkWindowBackend.available():
                raise RuntimeError("窗口捕获与输入组件（ok-script）不可用，请检查安装环境。")
        except (ValueError, RuntimeError) as error:
            self._emit(EventKind.WARNING, f"无法启动自动制作：{error}")
            return False
        if self._enabled.is_set() or self._shutdown.is_set() or generation != self._interrupt_generation:
            return False
        self._interrupt_generation += 1
        self._craft_request = (session, target)
        self._cleanup_test_requested.clear()
        self._enabled.set()
        self._emit_crafting(session.progress(time.monotonic(), self._interrupt_generation), log=True)
        return True

    def request_inventory_cleanup_test(self) -> bool:
        with self._config_lock:
            return self._request_inventory_cleanup_test()

    def _request_inventory_cleanup_test(self) -> bool:
        """独立执行一次真实整理测试；不依赖正式自动清理开关。"""
        config = self.config()
        if self._enabled.is_set():
            self._emit(
                EventKind.WARNING,
                "请先暂停普通监测，再启动背包清理调试。",
            )
            return False
        missing_calibration = (
            config.target_button_offset is None
            if config.capture_mode == "window"
            else config.button_center is None
        )
        if missing_calibration:
            self._emit(
                EventKind.WARNING,
                "背包清理调试需要先完成 F7 校准。",
            )
            return False
        if config.capture_mode == "window":
            try:
                self._resolve_target_window(config)
            except RuntimeError as error:
                self._emit(
                    EventKind.WARNING,
                    f"无法启动背包清理调试：{error}",
                )
                return False
        self._reset_detection()
        self._cleanup_test_requested.set()
        self._enabled.set()
        self._emit(
            EventKind.STATE,
            "背包清理调试：已独立排队，不会开启正式自动清理功能；正在准备真实整理测试。",
            monitoring=True,
        )
        return True
