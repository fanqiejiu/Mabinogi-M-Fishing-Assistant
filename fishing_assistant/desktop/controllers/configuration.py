"""配置加载、控件连接、窗口和分辨率联动"""
from __future__ import annotations
from fishing_assistant.desktop.terminology import (
    WINDOW_CAPTURE_DESCRIPTIONS, WINDOW_INPUT_DESCRIPTION,
    ICON_RECOGNITION_LABELS, ICON_MATCH_SCORE_LABEL,
)

import mss
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget
from fishing_assistant import window_target
from fishing_assistant.config import (
    AppConfig,
    default_config,
    effective_roi_size,
    parse_resolution,
    resolution_label_for_size,
)
from fishing_assistant.engine import EventKind


class ConfigurationControllerMixin:
    """配置加载、控件连接、窗口和分辨率联动；由 MainWindow 组装，不单独实例化。"""

    def _populate_display_options(self) -> None:
        self.monitor_combo.clear()
        resolutions = ["1920 × 1080", "2560 × 1440", "3840 × 2160"]
        try:
            with mss.MSS() as screen:
                monitors = screen.monitors[1:]
            for index, monitor in enumerate(monitors, start=1):
                width, height = int(monitor["width"]), int(monitor["height"])
                resolution = f"{width} × {height}"
                self.monitor_combo.addItem(f"显示器 {index}  ·  {resolution}", index)
                if resolution not in resolutions:
                    resolutions.insert(0, resolution)
        except Exception:
            self.monitor_combo.addItem("显示器 1", 1)
        self.resolution_combo.clear()
        self.resolution_combo.addItems(resolutions)
        self._refresh_target_windows()

    def _refresh_target_windows(self, *_: object) -> None:
        if self.engine.is_monitoring() is True:
            return
        config = self.engine.config()
        current_handle = config.target_window_handle
        current_title = config.target_window_title
        blocker = QSignalBlocker(self.target_window_combo)
        self.target_window_combo.clear()
        try:
            windows = window_target.list_target_windows(include_minimized=True)
            self._target_discovery_error = ""
        except Exception as error:  # pragma: no cover - 由 Windows 会话状态决定
            windows = []
            self._target_discovery_error = f"无法读取窗口列表：{error}"
        windows = [target for target in windows if target.title != self.windowTitle()]
        preferred_target = window_target.select_target_window(windows, current_handle, current_title)
        self._auto_detected_game_window = window_target.find_mabinogi_mobile_window(windows)
        for target in windows:
            self.target_window_combo.addItem(
                target.display_label, target
            )
        if self.target_window_combo.count() == 0:
            self.target_window_combo.addItem("未发现可选窗口，请打开洛奇 M 后刷新", None)
        if preferred_target is not None:
            self._select_target_window(preferred_target.handle, preferred_target.title)
        else:
            self._select_target_window(current_handle, current_title)
        del blocker
        if preferred_target is not None:
            self.engine.update_config(
                target_window_handle=preferred_target.handle,
                target_window_title=preferred_target.title,
            )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()

    def _select_target_window(self, handle: int, title: str) -> None:
        windows = [self.target_window_combo.itemData(index)
                   for index in range(self.target_window_combo.count())]
        target = window_target.select_target_window(
            [item for item in windows if isinstance(item, window_target.WindowInfo)], handle, title)
        self.target_window_combo.setCurrentIndex(windows.index(target) if target is not None else -1)

    def _sync_auto_roi_controls(self) -> None:
        automatic = self.auto_roi_check.isChecked()
        target = self.target_window_combo.currentData()
        has_target = isinstance(target, window_target.WindowInfo) and not target.minimized
        self.resolution_combo.setEnabled(not automatic or not has_target)
        self.roi_width_spin.setEnabled(not automatic)
        self.roi_height_spin.setEnabled(not automatic)
        if not automatic:
            self.roi_mode_hint.setText(
                f"当前为手动模式：识别区域 {self.roi_width_spin.value()} × "
                f"{self.roi_height_spin.value()} px。"
            )
            return

        if isinstance(target, window_target.WindowInfo) and target.minimized:
            self.roi_mode_hint.setText("游戏已最小化，恢复窗口后再匹配分辨率。")
            return

        config = self.engine.config()
        source_resolution: tuple[int, int] | None = None
        source_text = "所选画面"
        if isinstance(target, window_target.WindowInfo):
            source_resolution = (target.width, target.height)
            profile_label = resolution_label_for_size(target.width, target.height)
            resolution_blocker = QSignalBlocker(self.resolution_combo)
            self._select_combo_text(self.resolution_combo, profile_label)
            del resolution_blocker
            if config.selected_resolution != profile_label:
                config = self.engine.update_config(
                    selected_resolution=profile_label
                )
            source_text = (
                f"已检测游戏窗口 {target.width} × {target.height}，"
                f"匹配 {profile_label}"
            )
        else:
            selected = self.resolution_combo.currentText()
            source_resolution = parse_resolution(selected)
            source_text = f"按所选画面 {selected}"

        roi_width, roi_height = effective_roi_size(config, source_resolution)
        width_blocker = QSignalBlocker(self.roi_width_spin)
        height_blocker = QSignalBlocker(self.roi_height_spin)
        self.roi_width_spin.setValue(roi_width)
        self.roi_height_spin.setValue(roi_height)
        del width_blocker, height_blocker
        self.roi_mode_hint.setText(
            f"{source_text}，识别区域自动设为 {roi_width} × {roi_height} px。"
        )

    def _auto_roi_toggled(self, checked: bool) -> None:
        if checked:
            self.engine.update_config(auto_scale_roi=True)
        else:
            self.engine.update_config(
                auto_scale_roi=False,
                roi_width=self.roi_width_spin.value(),
                roi_height=self.roi_height_spin.value(),
            )
        self._sync_auto_roi_controls()

    def _sync_target_mode_controls(self) -> None:
        is_window_mode = self.target_mode_combo.currentData() == "window"
        if not is_window_mode and hasattr(self, "profile_details"):
            self.profile_details.toggle.setChecked(True)
        self.backend_options_panel.setProperty("modeActive", is_window_mode)
        self.backend_options_panel.setEnabled(is_window_mode)
        self.backend_options_panel.setVisible(is_window_mode)
        self.backend_mode_badge.setText(
            "窗口捕获与输入" if is_window_mode else "屏幕捕获与输入"
        )
        for widget in [
            self.backend_options_panel,
            *self.backend_options_panel.findChildren(QWidget),
        ]:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        if is_window_mode:
            target = self.target_window_combo.currentData()
            if isinstance(target, window_target.WindowInfo):
                if (
                    self._auto_detected_game_window is not None
                    and target.handle == self._auto_detected_game_window.handle
                ):
                    selection = f"已自动检测窗口名称“瑪奇 Mobile”：{target.title}。"
                else:
                    selection = f"当前手动目标：{target.title}。"
            else:
                selection = "未检测到“瑪奇 Mobile”，请从下拉列表选择游戏窗口。"
            backend = str(self.window_backend_combo.currentData())
            self.target_mode_status.setToolTip(
                WINDOW_CAPTURE_DESCRIPTIONS[backend]
                + WINDOW_INPUT_DESCRIPTION
                + "请保持洛奇 M 窗口未最小化；临时错误会按设置重试，达到上限后停止任务。"
                + selection
            )
            self.target_mode_status.setText(
                "游戏已最小化，请恢复窗口后刷新。" if isinstance(target, window_target.WindowInfo) and target.minimized
                else "游戏可被遮挡，请勿最小化。" if isinstance(target, window_target.WindowInfo)
                else "未找到游戏窗口，请选择或刷新。"
            )
            if getattr(self, "_target_discovery_error", ""):
                self.target_mode_status.setText(self._target_discovery_error)
        else:
            self.target_mode_status.setText(
                "前台模式：请保持游戏在前台。"
            )
            self.target_mode_status.setToolTip("捕获所选显示器画面，并使用系统键鼠输入。必须保持游戏位于前台，否则可能操作到其他程序。")

    def _target_mode_changed(self) -> None:
        self._sync_target_mode_controls()
        self._save_profile()

    def _load_config(self, config: AppConfig) -> None:
        controls = [
            self.monitor_combo,
            self.mode_combo,
            self.resolution_combo,
            self.target_mode_combo,
            self.window_backend_combo,
            self.target_window_combo,
            self.recognition_backend_combo,
            self.threshold_slider,
            self.auto_roi_check,
            self.roi_width_spin,
            self.roi_height_spin,
            self.interval_combo,
            self.trigger_spin,
            self.clear_spin,
            self.cooldown_spin,
            self.runtime_retry_spin,
            self.catch_strategy_combo,
            self.fallback_delay_spin,
            self.latest_collect_spin,
            self.stamina_zoom_spin,
            self.auto_resume_check,
            self.auto_recover_check,
            self.recovery_mode_combo,
            self.idle_min_spin,
            self.idle_max_spin,
            self.recovery_hold_spin,
            self.recovery_cooldown_spin,
            self.recovery_attempt_limit_spin,
            self.recovery_forward_interval_spin,
            self.recovery_forward_taps_spin,
            self.recovery_w_only_count_spin,
            self.recovery_w_only_hold_spin,
            self.inventory_cleanup_check,
            self.voice_alerts_check,
            self.voice_character_combo,
            self.floating_status_check,
            self.floating_opacity_slider,
            self.github_auto_check,
        ]
        blockers = [QSignalBlocker(control) for control in controls]
        self._select_combo_data(self.monitor_combo, config.monitor_index)
        self._select_combo_data(self.mode_combo, config.display_mode)
        self._select_combo_data(self.target_mode_combo, config.capture_mode)
        self._select_combo_data(self.window_backend_combo, config.window_backend)
        self._select_combo_data(
            self.recognition_backend_combo, config.recognition_backend
        )
        self._select_target_window(config.target_window_handle, config.target_window_title)
        self._select_combo_text(self.resolution_combo, config.selected_resolution)
        self.threshold_slider.setValue(config.fish_red_pixel_threshold)
        self.auto_roi_check.setChecked(config.auto_scale_roi)
        self.roi_width_spin.setValue(config.roi_width)
        self.roi_height_spin.setValue(config.roi_height)
        self._select_combo_data(self.interval_combo, config.poll_interval_ms)
        self.trigger_spin.setValue(config.trigger_consecutive_frames)
        self.clear_spin.setValue(config.clear_consecutive_frames)
        self.cooldown_spin.setValue(config.press_cooldown_ms)
        self.runtime_retry_spin.setValue(config.runtime_error_retry_count)
        self._select_combo_data(self.catch_strategy_combo, config.catch_strategy)
        self.fallback_delay_spin.setValue(config.fallback_collect_delay_seconds)
        self.latest_collect_spin.setValue(
            config.fixed_delay_latest_collect_seconds
        )
        self.stamina_zoom_spin.setValue(config.stamina_zoom_in_steps)
        self.auto_resume_check.setChecked(config.auto_resume_fishing)
        self.auto_recover_check.setChecked(config.auto_recover_idle)
        self._select_combo_data(
            self.recovery_mode_combo, config.recovery_movement_mode
        )
        self.idle_min_spin.setValue(config.idle_red_pixel_min)
        self.idle_max_spin.setValue(config.idle_red_pixel_max)
        self.recovery_hold_spin.setValue(config.recovery_key_hold_ms)
        self.recovery_cooldown_spin.setValue(config.recovery_cooldown_ms)
        self.recovery_attempt_limit_spin.setValue(config.recovery_attempt_limit)
        self.recovery_forward_interval_spin.setValue(
            config.recovery_forward_compensation_interval
        )
        self.recovery_forward_taps_spin.setValue(
            config.recovery_forward_compensation_taps
        )
        self.recovery_w_only_count_spin.setValue(config.recovery_w_only_count)
        self.recovery_w_only_hold_spin.setValue(
            config.recovery_w_only_hold_seconds
        )
        self.inventory_cleanup_check.setChecked(
            config.inventory_auto_cleanup_enabled
        )
        self.voice_alerts_check.setChecked(config.voice_alerts_enabled)
        self._select_combo_data(
            self.voice_character_combo, config.voice_character
        )
        self.floating_status_check.setChecked(config.floating_status_enabled)
        self.floating_opacity_slider.setValue(config.floating_status_opacity)
        self.github_auto_check.setChecked(config.github_auto_check)
        del blockers
        selected_voice = str(self.voice_character_combo.currentData() or "")
        if selected_voice and selected_voice != config.voice_character:
            self.engine.update_config(voice_character=selected_voice)
        self.voice_player.configure(
            config.voice_alerts_enabled,
            selected_voice,
        )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()
        self._sync_catch_strategy_controls()
        self._sync_recovery_mode_controls()
        self._sync_recognition_backend_controls()
        self._refresh_threshold_display(config.fish_red_pixel_threshold)
        self._sync_floating_status_controls()
        self._sync_floating_status_visibility()
        self._sync_inventory_cleanup_debug_controls()
        self._sync_voice_controls()

    def _connect_controls(self) -> None:
        self.monitor_combo.currentIndexChanged.connect(self._save_profile)
        self.mode_combo.currentIndexChanged.connect(self._save_profile)
        self.resolution_combo.currentIndexChanged.connect(self._save_profile)
        self.target_mode_combo.currentIndexChanged.connect(self._target_mode_changed)
        self.window_backend_combo.currentIndexChanged.connect(self._target_mode_changed)
        self.target_window_combo.currentIndexChanged.connect(self._save_profile)
        self.refresh_windows_button.clicked.connect(self._refresh_target_windows)
        self.calibrate_button.clicked.connect(self._calibrate)
        self.start_button.clicked.connect(self._toggle_monitoring)
        self.snapshot_button.clicked.connect(self.engine.request_debug_capture)
        self.view_snapshot_button.clicked.connect(self._view_snapshot)
        self.open_snapshot_folder_button.clicked.connect(self._open_snapshot_directory)
        self.theme_button.clicked.connect(self._toggle_theme)
        self.floating_status_button.toggled.connect(
            self.floating_status_check.setChecked
        )
        self.recognition_backend_combo.currentIndexChanged.connect(
            self._recognition_backend_changed
        )
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        self.auto_roi_check.toggled.connect(self._auto_roi_toggled)
        self.roi_width_spin.valueChanged.connect(lambda value: self.engine.update_config(roi_width=value))
        self.roi_height_spin.valueChanged.connect(lambda value: self.engine.update_config(roi_height=value))
        self.interval_combo.currentIndexChanged.connect(
            lambda: self.engine.update_config(poll_interval_ms=int(self.interval_combo.currentData()))
        )
        self.trigger_spin.valueChanged.connect(
            lambda value: self.engine.update_config(trigger_consecutive_frames=value)
        )
        self.clear_spin.valueChanged.connect(
            lambda value: self.engine.update_config(clear_consecutive_frames=value)
        )
        self.cooldown_spin.valueChanged.connect(
            lambda value: self.engine.update_config(press_cooldown_ms=value)
        )
        self.runtime_retry_spin.valueChanged.connect(
            lambda value: self.engine.update_config(runtime_error_retry_count=value)
        )
        self.catch_strategy_combo.currentIndexChanged.connect(self._catch_strategy_changed)
        self.fallback_delay_spin.valueChanged.connect(
            self._fallback_delay_changed
        )
        self.latest_collect_spin.valueChanged.connect(
            self._latest_collect_changed
        )
        self.stamina_zoom_spin.valueChanged.connect(
            lambda value: self.engine.update_config(stamina_zoom_in_steps=value)
        )
        self.auto_resume_check.toggled.connect(
            lambda checked: self.engine.update_config(auto_resume_fishing=checked)
        )
        self.auto_recover_check.toggled.connect(
            lambda checked: self.engine.update_config(auto_recover_idle=checked)
        )
        self.recovery_mode_combo.currentIndexChanged.connect(
            self._recovery_mode_changed
        )
        self.idle_min_spin.valueChanged.connect(
            lambda value: self.engine.update_config(idle_red_pixel_min=value)
        )
        self.idle_max_spin.valueChanged.connect(
            lambda value: self.engine.update_config(idle_red_pixel_max=value)
        )
        self.recovery_hold_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_key_hold_ms=value)
        )
        self.recovery_cooldown_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_cooldown_ms=value)
        )
        self.recovery_attempt_limit_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_attempt_limit=value)
        )
        self.recovery_forward_interval_spin.valueChanged.connect(
            lambda value: self.engine.update_config(
                recovery_forward_compensation_interval=value
            )
        )
        self.recovery_forward_taps_spin.valueChanged.connect(
            lambda value: self.engine.update_config(
                recovery_forward_compensation_taps=value
            )
        )
        self.recovery_w_only_count_spin.valueChanged.connect(
            lambda value: self.engine.update_config(recovery_w_only_count=value)
        )
        self.recovery_w_only_hold_spin.valueChanged.connect(
            lambda value: self.engine.update_config(
                recovery_w_only_hold_seconds=float(value)
            )
        )
        self.inventory_cleanup_check.toggled.connect(
            self._inventory_cleanup_toggled
        )
        self.test_inventory_cleanup_button.clicked.connect(
            self._test_inventory_cleanup
        )
        self.restore_button.clicked.connect(self._restore_recommended_settings)

        self.voice_alerts_check.toggled.connect(
            self._voice_alerts_toggled
        )
        self.voice_character_combo.currentIndexChanged.connect(
            self._voice_character_changed
        )
        self.voice_preview_button.clicked.connect(self._preview_voice)

        self.floating_status_check.toggled.connect(
            self._floating_status_toggled
        )
        self.floating_opacity_slider.valueChanged.connect(
            self._floating_opacity_changed
        )
        self.check_update_button.clicked.connect(lambda: self._check_for_updates(manual=True))
        self.github_auto_check.toggled.connect(
            lambda checked: self.engine.update_config(github_auto_check=checked)
        )
        self.open_release_button.clicked.connect(self._open_release_page)
        self.create_bundle_button.clicked.connect(self._create_diagnostic_bundle)
        self.open_log_button.clicked.connect(self._open_log_directory)

    def _save_profile(self) -> None:
        config = self.engine.config()
        target = self.target_window_combo.currentData()
        target_handle = config.target_window_handle
        target_title = config.target_window_title
        if isinstance(target, window_target.WindowInfo):
            target_handle = target.handle
            target_title = target.title
        self.engine.update_config(
            monitor_index=int(self.monitor_combo.currentData() or 1),
            display_mode=str(self.mode_combo.currentData()),
            selected_resolution=self.resolution_combo.currentText(),
            capture_mode=str(self.target_mode_combo.currentData()),
            window_backend=str(self.window_backend_combo.currentData()),
            target_window_handle=target_handle,
            target_window_title=target_title,
        )
        self._sync_target_mode_controls()
        self._sync_auto_roi_controls()
        self._refresh_calibration_summary()
        self._sync_floating_status_visibility()

    def _recognition_backend_changed(self) -> None:
        backend = str(self.recognition_backend_combo.currentData() or "ok")
        self.engine.update_config(recognition_backend=backend)
        self._sync_recognition_backend_controls()
        mode_name = ICON_RECOGNITION_LABELS[backend]
        self._append_log(
            f"图标识别模式已切换为“{mode_name}”；两种模式不会自动互相回退。",
            EventKind.INFO,
        )

    def _sync_recognition_backend_controls(self) -> None:
        use_pixel = self.recognition_backend_combo.currentData() == "pixel"
        self.pixel_fish_threshold_panel.setVisible(use_pixel)
        self.pixel_compass_threshold_panel.setVisible(use_pixel)
        self.recognition_backend_hint.setText("识别失败时不会自动切换方式。")
        for control in (
            self.threshold_header_label,
            self.threshold_value,
            self.threshold_slider,
            self.idle_min_spin,
            self.idle_max_spin,
        ):
            control.setEnabled(use_pixel)
        if use_pixel:
            self.recognition_backend_combo.setToolTip(
                "根据红、白、绿、蓝、棕色像素判断图标，不进行图像模板匹配；此设置不改变窗口捕获方式。"
            )
            self.red_metric.caption_label.setText("当前红色像素")
            self.red_metric.value_label.setText("0 px")
            self.red_progress.setMaximum(
                max(1, self.engine.config().fish_red_pixel_threshold)
            )
        else:
            self.recognition_backend_combo.setToolTip(
                "由 ok-script 的 FeatureSet 进行图像模板匹配；旋转指南针保留中心黑点像素校正。此设置不改变窗口捕获方式。"
            )
            self.red_metric.caption_label.setText(ICON_MATCH_SCORE_LABEL)
            self.red_metric.value_label.setText("等待识别")
            self.red_progress.setMaximum(1000)
        self.red_progress.setValue(0)

    def _threshold_changed(self, value: int) -> None:
        self.engine.update_config(fish_red_pixel_threshold=value)
        self._refresh_threshold_display(value)

    def _restore_recommended_settings(self) -> None:
        defaults = default_config()
        self.engine.update_config(
            recognition_backend=defaults.recognition_backend,
            roi_width=defaults.roi_width,
            roi_height=defaults.roi_height,
            auto_scale_roi=defaults.auto_scale_roi,
            poll_interval_ms=defaults.poll_interval_ms,
            fish_red_pixel_threshold=defaults.fish_red_pixel_threshold,
            idle_red_pixel_min=defaults.idle_red_pixel_min,
            idle_red_pixel_max=defaults.idle_red_pixel_max,
            trigger_consecutive_frames=defaults.trigger_consecutive_frames,
            clear_consecutive_frames=defaults.clear_consecutive_frames,
            press_cooldown_ms=defaults.press_cooldown_ms,
            runtime_error_retry_count=defaults.runtime_error_retry_count,
            auto_resume_fishing=defaults.auto_resume_fishing,
            auto_recover_idle=defaults.auto_recover_idle,
            recovery_consecutive_frames=defaults.recovery_consecutive_frames,
            recovery_key_hold_ms=defaults.recovery_key_hold_ms,
            recovery_pause_ms=defaults.recovery_pause_ms,
            recovery_cooldown_ms=defaults.recovery_cooldown_ms,
            recovery_attempt_limit=defaults.recovery_attempt_limit,
            recovery_forward_compensation_interval=(
                defaults.recovery_forward_compensation_interval
            ),
            recovery_forward_compensation_taps=(
                defaults.recovery_forward_compensation_taps
            ),
            recovery_movement_mode=defaults.recovery_movement_mode,
            recovery_w_only_count=defaults.recovery_w_only_count,
            recovery_w_only_hold_seconds=defaults.recovery_w_only_hold_seconds,
            catch_strategy=defaults.catch_strategy,
            fallback_collect_delay_seconds=defaults.fallback_collect_delay_seconds,
            fixed_delay_latest_collect_seconds=(
                defaults.fixed_delay_latest_collect_seconds
            ),
            stamina_scan_interval_ms=defaults.stamina_scan_interval_ms,
            stamina_zoom_in_steps=defaults.stamina_zoom_in_steps,
            inventory_auto_cleanup_enabled=(
                defaults.inventory_auto_cleanup_enabled
            ),
        )
        self._load_config(self.engine.config())
        self._append_log("已恢复推荐识别参数。", EventKind.INFO)
