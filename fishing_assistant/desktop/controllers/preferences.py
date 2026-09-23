"""语音、悬浮栏和主题偏好的交互"""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QIcon
from fishing_assistant.constants import resource_path
from fishing_assistant.desktop.styles import DAY_STYLE, NIGHT_STYLE
from fishing_assistant.engine import EventKind
from fishing_assistant.voice_alerts import F7_CALIBRATION_CUE


class PreferencesControllerMixin:
    """语音、悬浮栏和主题偏好的交互；由 MainWindow 组装，不单独实例化。"""

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
        self.voice_status.setVisible(True)
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
            self.voice_status.clear()
            self.voice_character_combo.setToolTip(f"{character} · {cue_count} 类提示")
        self.voice_status.setVisible(not enabled or not has_pack)

    def _floating_status_toggled(self, checked: bool) -> None:
        self.engine.update_config(floating_status_enabled=checked)
        self._sync_floating_status_controls()
        self._sync_floating_status_visibility()

    def _floating_opacity_changed(self, value: int) -> None:
        self.engine.update_config(floating_status_opacity=value)
        self._sync_floating_status_controls()

    def _sync_floating_status_controls(self) -> None:
        enabled = self.floating_status_check.isChecked()
        if hasattr(self, "floating_status_button"):
            blocker = QSignalBlocker(self.floating_status_button)
            self.floating_status_button.setChecked(enabled)
            del blocker
            self.floating_status_button.setText(
                "悬浮栏 · 开" if enabled else "悬浮栏 · 关"
            )
            self.floating_status_button.setToolTip(
                "关闭最小化后的悬浮状态栏。"
                if enabled
                else "开启最小化后的悬浮状态栏。"
            )
        opacity = self.floating_opacity_slider.value()
        self.floating_opacity_panel.setEnabled(enabled)
        self.floating_opacity_value.setText(f"{opacity}%")
        self.floating_status_bar.set_background_opacity(opacity)

    def _sync_floating_calibration_state(self) -> None:
        if self.engine.is_crafting() is True:
            self.floating_status_bar.set_crafting_target()
            return
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
        crafting = self.engine.is_crafting() is True
        minimized = self.isMinimized()
        if crafting:
            self._floating_crafting_session = True
        elif not minimized or self.engine.is_monitoring() is True:
            self._floating_crafting_session = False
        should_show = (
            config.floating_status_enabled
            and (config.capture_mode == "window" or crafting
                 or getattr(self, "_floating_crafting_session", False))
            and minimized
        )
        if should_show:
            if not self.floating_status_bar.isVisible():
                self.floating_status_bar.show_at_default_position()
        else:
            self.floating_status_bar.hide()

    def _toggle_theme(self) -> None:
        next_theme = "day" if self.engine.config().ui_theme == "night" else "night"
        self.engine.update_config(ui_theme=next_theme)
        self._apply_theme(next_theme)
        self._append_log(
            "已切换为日间界面。" if next_theme == "day" else "已切换为夜间界面。",
            EventKind.INFO,
        )

    def _apply_theme(self, theme: str) -> None:
        is_day = theme == "day"
        # 清除缓存后整页应用，避免隐藏页面/禁用按钮保留上一主题颜色。
        self.setStyleSheet("")
        self.setStyleSheet(DAY_STYLE if is_day else NIGHT_STYLE)
        if hasattr(self, "crafting_page"):
            self.crafting_page.set_theme(theme)
        if hasattr(self, "remote_panel"):
            self.remote_panel.set_theme(theme)
        self.floating_status_bar.set_theme(theme)
        self.theme_button.setText("夜间模式" if is_day else "日间模式")
        self.theme_button.setIcon(QIcon(str(resource_path("fishing_assistant", "assets", "theme.svg"))))
        self.theme_button.setToolTip("切换至夜间模式" if is_day else "切换至日间模式")
