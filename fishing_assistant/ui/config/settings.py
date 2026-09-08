"""语音提醒和悬浮状态栏配置。"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QDialog

from ...voice_alerts import F7_CALIBRATION_CUE


class SettingsConfigurationMixin:
    def _voice_alerts_toggled(self, checked: bool) -> None:
        character = str(self.voice_character_combo.currentData() or "")
        self.engine.update_config(voice_alerts_enabled=checked)
        self.voice_player.configure(checked, character)
        self._sync_voice_controls()

    def _voice_character_changed(self) -> None:
        character = str(self.voice_character_combo.currentData() or "")
        if character:
            self.engine.update_config(voice_character=character)
        self.voice_player.configure(
            self.voice_alerts_check.isChecked(), character
        )
        self._sync_voice_controls()

    def _preview_voice(self) -> None:
        selected = self.voice_player.play(F7_CALIBRATION_CUE)
        if selected is None:
            self.voice_status.setText(
                "当前音色没有可播放的 F7 定位语音，或相同提示仍在播放。"
            )
            return
        self.voice_status.setText(f"正在试听：{selected.name}")

    def _sync_voice_controls(self) -> None:
        character = str(self.voice_character_combo.currentData() or "")
        enabled = self.voice_alerts_check.isChecked()
        has_pack = bool(character)
        self.voice_character_combo.setEnabled(enabled and has_pack)
        self.voice_preview_button.setEnabled(enabled and has_pack)
        if not has_pack:
            self.voice_status.setText(
                "未找到语音包，请按 voice/人物名/事件名.wav 放置文件。"
            )
        elif not enabled:
            self.voice_status.setText("语音提醒已关闭。")
        else:
            cue_count = len(self.voice_player.cues_for(character))
            self.voice_status.setText(
                f"当前音色：{character} · 已识别 {cue_count} 类提示"
            )

    def _floating_status_toggled(self, checked: bool) -> None:
        self.engine.update_config(floating_status_enabled=checked)
        self._sync_floating_status_controls()
        self._sync_floating_status_visibility()

    def _floating_opacity_changed(self, value: int) -> None:
        self.engine.update_config(floating_status_opacity=value)
        self._sync_floating_status_controls()

    def _sync_floating_status_controls(self) -> None:
        enabled = self.floating_status_check.isChecked()
        opacity = self.floating_opacity_slider.value()
        self.floating_opacity_panel.setEnabled(enabled)
        self.floating_opacity_value.setText(f"{opacity}%")
        self.floating_status_bar.set_background_opacity(opacity)

    def _sync_floating_calibration_state(self) -> None:
        config = self.engine.config()
        calibrated = (
            config.target_button_offset is not None
            if config.capture_mode == "window"
            else config.button_center is not None
        )
        self.floating_status_bar.set_calibrated(calibrated)

    def _sync_floating_status_visibility(self) -> None:
        self._sync_floating_calibration_state()
        config = self.engine.config()
        should_show = (
            config.floating_status_enabled
            and config.capture_mode == "window"
            and self.isMinimized()
        )
        if should_show:
            self.floating_status_bar.show_at_default_position()
        else:
            self.floating_status_bar.hide()

