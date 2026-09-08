"""控制台配置与目标窗口设置。"""

from __future__ import annotations

import mss
from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import QWidget

from ... import window_target
from ...config import effective_roi_size, parse_resolution, resolution_label_for_size


class ProfileConfigurationMixin:
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
        config = self.engine.config()
        current_handle = config.target_window_handle
        current_title = config.target_window_title
        blocker = QSignalBlocker(self.target_window_combo)
        self.target_window_combo.clear()
        try:
            windows = window_target.list_target_windows()
        except Exception as error:  # pragma: no cover - 由 Windows 会话状态决定
            windows = []
            self.target_mode_status.setText(f"无法读取窗口列表：{error}")
        windows = [target for target in windows if target.title != self.windowTitle()]
        preferred_target = window_target.find_mabinogi_mobile_window(windows)
        self._auto_detected_game_window = preferred_target
        for target in windows:
            self.target_window_combo.addItem(
                f"{target.title}  ·  {target.width} × {target.height}", target
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
        for index in range(self.target_window_combo.count()):
            target = self.target_window_combo.itemData(index)
            if not isinstance(target, window_target.WindowInfo):
                continue
            if target.handle == handle or (title and target.title == title):
                self.target_window_combo.setCurrentIndex(index)
                return

    def _sync_auto_roi_controls(self) -> None:
        automatic = self.auto_roi_check.isChecked()
        target = self.target_window_combo.currentData()
        has_target = isinstance(target, window_target.WindowInfo)
        self.resolution_combo.setEnabled(not automatic or not has_target)
        self.roi_width_spin.setEnabled(not automatic)
        self.roi_height_spin.setEnabled(not automatic)
        if not automatic:
            self.roi_mode_hint.setText(
                f"当前为手动模式：识别区域 {self.roi_width_spin.value()} × "
                f"{self.roi_height_spin.value()} px。"
            )
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
        self.backend_options_panel.setProperty("modeActive", is_window_mode)
        self.backend_options_panel.setEnabled(is_window_mode)
        self.backend_mode_badge.setText(
            "● 后台设置已启用" if is_window_mode else "○ 当前为屏幕坐标模式"
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
            engine_text = (
                "OK 后台引擎：由 ok-script 提供 WGC 截图、虚拟悬停与 WM_ACTIVATE + PostMessage；"
                if backend == "ok"
                else "兼容引擎：使用 PrintWindow 截图与 WM_ACTIVATE + PostMessage；"
            )
            self.target_mode_status.setText(
                engine_text
                + "Space / W / S 和虚拟悬停只发送至这个窗口，真实鼠标可自由操作其他程序。"
                "请保持洛奇 M 窗口未最小化；临时错误会按设置重试，达到上限后暂停。"
                + selection
            )
        else:
            self.target_mode_status.setText(
                "前台屏幕坐标模式：识别与按键依赖洛奇 M 位于前台，不会在后台向其他窗口发送按键。"
            )

    def _target_mode_changed(self) -> None:
        self._sync_target_mode_controls()
        self._save_profile()

