"""识别引擎和阈值配置。"""

from __future__ import annotations

from ...config import default_config
from ...engine import EventKind


class ThresholdConfigurationMixin:
    def _recognition_backend_changed(self) -> None:
        backend = str(self.recognition_backend_combo.currentData() or "ok")
        self.engine.update_config(recognition_backend=backend)
        self._sync_recognition_backend_controls()
        mode_name = "OK 框架特征识别" if backend == "ok" else "旧版像素识别"
        self._append_log(
            f"图标识别模式已切换为“{mode_name}”；两种模式不会自动互相回退。",
            EventKind.INFO,
        )

    def _sync_recognition_backend_controls(self) -> None:
        use_pixel = self.recognition_backend_combo.currentData() == "pixel"
        self.pixel_fish_threshold_panel.setVisible(use_pixel)
        for control in (
            self.threshold_header_label,
            self.threshold_value,
            self.threshold_slider,
            self.idle_min_spin,
            self.idle_max_spin,
        ):
            control.setEnabled(use_pixel)
        if use_pixel:
            self.recognition_backend_hint.setText(
                "当前使用旧版像素兼容模式：根据红、白、绿、蓝、棕色像素判断图标；不会调用 OK 图标模板。"
            )
            self.red_metric.caption_label.setText("当前红色像素")
            self.red_metric.value_label.setText("0 px")
            self.red_progress.setMaximum(
                max(1, self.engine.config().fish_red_pixel_threshold)
            )
        else:
            self.recognition_backend_hint.setText(
                "当前使用 OK 框架：钓鱼、上钩和骑马图标由 FeatureSet 识别；旋转指南针单独使用中心黑点像素校正。"
            )
            self.red_metric.caption_label.setText("OK 特征相似度")
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

