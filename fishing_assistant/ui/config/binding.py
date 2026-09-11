"""配置加载与控件信号绑定。"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QDialog, QWidget

from ...config import AppConfig


class ConfigurationBindingMixin:
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
        self._load_profile_config(config)
        self._load_fishing_config(config)
        self._load_threshold_config(config)
        self._load_settings_config(config)
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

    def _load_profile_config(self, config: AppConfig) -> None:
        self._select_combo_data(self.monitor_combo, config.monitor_index)
        self._select_combo_data(self.mode_combo, config.display_mode)
        self._select_combo_data(self.target_mode_combo, config.capture_mode)
        self._select_combo_data(self.window_backend_combo, config.window_backend)
        self._select_target_window(config.target_window_handle, config.target_window_title)
        self._select_combo_text(self.resolution_combo, config.selected_resolution)

    def _load_fishing_config(self, config: AppConfig) -> None:
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

    def _load_threshold_config(self, config: AppConfig) -> None:
        self._select_combo_data(
            self.recognition_backend_combo, config.recognition_backend
        )
        self.threshold_slider.setValue(config.fish_red_pixel_threshold)
        self.auto_roi_check.setChecked(config.auto_scale_roi)
        self.roi_width_spin.setValue(config.roi_width)
        self.roi_height_spin.setValue(config.roi_height)
        self._select_combo_data(self.interval_combo, config.poll_interval_ms)
        self.trigger_spin.setValue(config.trigger_consecutive_frames)
        self.clear_spin.setValue(config.clear_consecutive_frames)
        self.cooldown_spin.setValue(config.press_cooldown_ms)
        self.runtime_retry_spin.setValue(config.runtime_error_retry_count)
        self.idle_min_spin.setValue(config.idle_red_pixel_min)
        self.idle_max_spin.setValue(config.idle_red_pixel_max)

    def _load_settings_config(self, config: AppConfig) -> None:
        self.voice_alerts_check.setChecked(config.voice_alerts_enabled)
        self._select_combo_data(
            self.voice_character_combo, config.voice_character
        )
        self.floating_status_check.setChecked(config.floating_status_enabled)
        self.floating_opacity_slider.setValue(config.floating_status_opacity)
        self.github_auto_check.setChecked(config.github_auto_check)

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
        self.floating_status_button.clicked.connect(self._toggle_floating_status)
        self.recognition_backend_combo.currentIndexChanged.connect(
            self._recognition_backend_changed
        )
        self.threshold_slider.valueChanged.connect(self._threshold_changed)
        self.auto_roi_check.toggled.connect(self._auto_roi_toggled)
        self.catch_strategy_combo.currentIndexChanged.connect(self._catch_strategy_changed)
        self.fallback_delay_spin.valueChanged.connect(
            self._fallback_delay_changed
        )
        self.latest_collect_spin.valueChanged.connect(
            self._latest_collect_changed
        )
        self.recovery_mode_combo.currentIndexChanged.connect(
            self._recovery_mode_changed
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
        self.open_release_button.clicked.connect(self._open_release_page)
        self.create_bundle_button.clicked.connect(self._create_diagnostic_bundle)
        self.open_log_button.clicked.connect(self._open_log_directory)
        self._bind_config_updates()

    def _bind_config_updates(self) -> None:
        bindings = (
            ("roi_width_spin", "valueChanged", "roi_width", None),
            ("roi_height_spin", "valueChanged", "roi_height", None),
            ("interval_combo", "currentIndexChanged", "poll_interval_ms", int),
            ("trigger_spin", "valueChanged", "trigger_consecutive_frames", None),
            ("clear_spin", "valueChanged", "clear_consecutive_frames", None),
            ("cooldown_spin", "valueChanged", "press_cooldown_ms", None),
            ("runtime_retry_spin", "valueChanged", "runtime_error_retry_count", None),
            ("stamina_zoom_spin", "valueChanged", "stamina_zoom_in_steps", None),
            ("auto_resume_check", "toggled", "auto_resume_fishing", None),
            ("auto_recover_check", "toggled", "auto_recover_idle", None),
            ("idle_min_spin", "valueChanged", "idle_red_pixel_min", None),
            ("idle_max_spin", "valueChanged", "idle_red_pixel_max", None),
            ("recovery_hold_spin", "valueChanged", "recovery_key_hold_ms", None),
            ("recovery_cooldown_spin", "valueChanged", "recovery_cooldown_ms", None),
            ("recovery_attempt_limit_spin", "valueChanged", "recovery_attempt_limit", None),
            (
                "recovery_forward_interval_spin",
                "valueChanged",
                "recovery_forward_compensation_interval",
                None,
            ),
            (
                "recovery_forward_taps_spin",
                "valueChanged",
                "recovery_forward_compensation_taps",
                None,
            ),
            ("recovery_w_only_count_spin", "valueChanged", "recovery_w_only_count", None),
            (
                "recovery_w_only_hold_spin",
                "valueChanged",
                "recovery_w_only_hold_seconds",
                float,
            ),
            ("github_auto_check", "toggled", "github_auto_check", None),
        )
        for control_name, signal_name, config_name, transform in bindings:
            control = getattr(self, control_name)
            signal = getattr(control, signal_name)
            if signal_name == "currentIndexChanged":
                signal.connect(
                    lambda _index, control=control, key=config_name, cast=transform:
                    self._update_combo_config(control, key, cast)
                )
            else:
                signal.connect(
                    lambda value, key=config_name, cast=transform:
                    self._update_config_value(key, value, cast)
                )

    def _update_config_value(
        self,
        config_name: str,
        value: object,
        transform: object = None,
    ) -> None:
        if transform is not None:
            value = transform(value)  # type: ignore[operator]
        self.engine.update_config(**{config_name: value})

    def _update_combo_config(
        self,
        control: QWidget,
        config_name: str,
        transform: object = None,
    ) -> None:
        value = control.currentData()  # type: ignore[attr-defined]
        self._update_config_value(config_name, value, transform)
