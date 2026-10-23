"""背包清理流程与大胆整理关闭的多重确认"""
from __future__ import annotations

import mss
import numpy as np
import time
from fishing_assistant.automation.models import EventKind, _CleanupCancelled, _OperationCancelled
from fishing_assistant.config import AppConfig
from fishing_assistant.inventory_cleanup import (
    BoldCleanupState,
    InventoryCleanupVision,
    SimpleCleanupState,
    TemplateMatch,
)
from typing import Callable


class InventoryCleanupMixin:
    """背包清理流程与大胆整理关闭的多重确认；由 FishingEngine 组装，不单独实例化。"""

    def _perform_inventory_cleanup(
        self,
        config: AppConfig,
        confidence: float,
        *,
        resume_fishing: bool = True,
    ) -> bool:
        """在独立安全确认链中执行四类简单整理；任一步不确定都会停机。"""
        generation = getattr(self._work_context, "generation", self._interrupt_generation)
        screen: mss.MSS | None = None
        self._inventory_full_hits = 0
        self._cleanup_in_progress.set()
        try:
            self._ensure_cleanup_active(generation)
            if config.capture_mode == "screen":
                screen = mss.MSS()
            self._emit(
                EventKind.STATE,
                (
                    "自动清理背包：已确认背包满，正在打开背包。"
                    if resume_fishing
                    else "背包清理调试：正在打开背包，执行一次真实整理测试。"
                ),
                monitoring=True,
            )
            self._ensure_cleanup_active(generation)
            initial_simple = self._open_cleanup_panel(screen, config, generation)
            self._emit(
                EventKind.STATE,
                "自动清理背包：正在关闭并反复核验“大胆整理”。",
                monitoring=True,
            )
            if initial_simple.bold_cleanup == BoldCleanupState.UNKNOWN:
                raise RuntimeError("无法判断“大胆整理”开关状态")
            if initial_simple.bold_cleanup == BoldCleanupState.ON:
                self._ensure_cleanup_active(generation)
                self._click_game_point(
                    initial_simple.toggle_center, config, screen
                )
                time.sleep(0.28)

            safe_simple = self._confirm_simple_cleanup_safety(
                screen,
                config,
                generation,
                reason="关闭“大胆整理”后",
            )
            self._emit(
                EventKind.INFO,
                "已连续 3 帧通过 OK 开关图案和颜色复核，确认“大胆整理”关闭。",
                monitoring=True,
            )

            category_names = ("装备", "材料", "黄金及杂物", "恢复道具")
            current_simple = safe_simple
            for category_index, category_name in enumerate(category_names):
                self._ensure_cleanup_active(generation)
                if not current_simple.selected_categories[category_index]:
                    self._click_game_point(
                        current_simple.category_centers[category_index],
                        config,
                        screen,
                    )
                    time.sleep(0.18)
                    frame = self._capture_stamina_frame(
                        screen, config
                    )[:, :, :3]
                    refreshed = InventoryCleanupVision.inspect_simple_screen(
                        frame
                    )
                    self._ensure_cleanup_active(generation)
                    if refreshed is None:
                        raise RuntimeError(
                            f"选择“{category_name}”后未识别到简单整理页面"
                        )
                    if refreshed.bold_cleanup != BoldCleanupState.OFF:
                        raise RuntimeError(
                            f"选择“{category_name}”后“大胆整理”不再是关闭状态"
                        )
                    current_simple = refreshed
            self._confirm_simple_cleanup_safety(
                screen,
                config,
                generation,
                require_ready=True,
                reason="选择四类简单整理项目后",
            )
            # 重中之重：临近不可逆操作前再重新抓取三帧，不复用旧结论。
            final_simple = self._confirm_simple_cleanup_safety(
                screen,
                config,
                generation,
                require_ready=True,
                reason="点击绿色整理按钮前",
            )
            selected_count = sum(final_simple.selected_categories)
            self._emit(
                EventKind.INFO,
                "最终安全核验通过：大胆整理已关闭，"
                f"{selected_count} 个有可整理项目的分类呈绿色，整理按钮可用。",
                monitoring=True,
            )
            self._ensure_cleanup_active(generation)
            self._click_game_point(final_simple.execute_center, config, screen)

            detail_frame, detail_match = self._wait_cleanup_screen(
                screen,
                config,
                generation,
                InventoryCleanupVision.find_detail,
                "整理对象确认页面",
            )
            self._emit(
                EventKind.STATE,
                "自动清理背包：整理对象页面已确认，正在执行四类简单整理。",
                monitoring=True,
            )
            self._ensure_cleanup_active(generation)
            self._click_game_point(
                self._bottom_center_button(detail_frame),
                config,
                screen,
            )

            result_frame, result_match = self._wait_cleanup_screen(
                screen,
                config,
                generation,
                InventoryCleanupVision.find_result,
                "整理完成页面",
            )
            self._emit(
                EventKind.INFO,
                "整理完成页面已确认："
                f"对象页 {detail_match.confidence:.3f}，完成页 {result_match.confidence:.3f}。",
                monitoring=True,
            )
            self._ensure_cleanup_active(generation)
            self._click_game_point(
                self._bottom_center_button(result_frame),
                config,
                screen,
            )
            _done_frame, done_match = self._wait_cleanup_screen(
                screen,
                config,
                generation,
                InventoryCleanupVision.find_done_toast,
                "“已整理背包”提示",
            )
            self._ensure_cleanup_active(generation)
            self._press_key("esc", config)
            time.sleep(0.25)
            self._ensure_cleanup_active(generation)
            self._restore_fishing_pointer(config)
            self._ensure_cleanup_active(generation)
            self._reset_detection()
            if resume_fishing:
                self._startup_probe_active = True
                self._schedule_recast(
                    time.monotonic(), config, "背包自动整理完成"
                )
                self._emit(
                    EventKind.SUCCESS,
                    "背包自动整理完成：已按关闭大胆整理后的四类简单整理规则处理；"
                    f"完成提示相似度 {done_match.confidence:.3f}，已退出背包并恢复钓鱼。",
                    monitoring=True,
                )
            else:
                self._enabled.clear()
                self._finish_fishing_session("inventory_test_completed")
                self._emit(
                    EventKind.SUCCESS,
                    "背包清理调试完成：已退出背包，普通监测保持暂停。"
                    f"完成提示相似度 {done_match.confidence:.3f}。",
                    monitoring=False,
                )
                self._emit(
                    EventKind.STATE,
                    "背包清理调试已完成，监测保持暂停。",
                    monitoring=False,
                )
            return True
        except _OperationCancelled:
            return True
        except Exception as error:
            if not self._operation_active(generation):
                return True
            self._interrupt_generation += 1
            self._enabled.clear()
            self._finish_fishing_session("inventory_error")
            self._reset_detection()
            self._emit(
                EventKind.ERROR,
                "背包自动整理已安全停止："
                f"{error}。没有继续执行后续整理点击，请手动检查当前游戏界面。"
                f"背包满提示相似度 {confidence:.3f}。",
                monitoring=False,
            )
            return True
        finally:
            self._cleanup_in_progress.clear()
            if screen is not None:
                screen.close()

    def _wait_cleanup_screen(
        self,
        screen: mss.MSS | None,
        config: AppConfig,
        generation: int,
        detector: Callable[[np.ndarray], TemplateMatch | SimpleCleanupState | None],
        description: str,
    ) -> tuple[np.ndarray, TemplateMatch | SimpleCleanupState]:
        deadline = time.monotonic() + self.CLEANUP_SCREEN_TIMEOUT_SECONDS
        attempts = 0
        last_log = 0.0
        size = "未知"
        while time.monotonic() < deadline:
            self._ensure_cleanup_active(generation)
            frame = self._capture_stamina_frame(screen, config)[:, :, :3]
            attempts += 1
            size = f"{frame.shape[1]}×{frame.shape[0]}"
            result = detector(frame)
            self._ensure_cleanup_active(generation)
            if result is not None:
                return frame, result
            now = time.monotonic()
            if now-last_log >= 1.5:
                scores = ", ".join(f"{key}={value:.2f}" for key,value in InventoryCleanupVision.last_scores.items())
                self._emit(EventKind.INFO, f"背包识别：等待{description}，第 {attempts} 帧，画面 {size}；OK {scores or '暂无匹配'}。", monitoring=True)
                last_log = now
            time.sleep(self.CLEANUP_CONFIRM_INTERVAL_SECONDS)
        raise RuntimeError(f"等待{description}超时（已检查 {attempts} 帧，画面 {size}）")

    def _confirm_simple_cleanup_safety(
        self,
        screen: mss.MSS | None,
        config: AppConfig,
        generation: int,
        *,
        require_ready: bool = False,
        reason: str,
    ) -> SimpleCleanupState:
        last: SimpleCleanupState | None = None
        for frame_number in range(1, self.CLEANUP_CONFIRM_FRAMES + 1):
            self._ensure_cleanup_active(generation)
            frame = self._capture_stamina_frame(screen, config)[:, :, :3]
            state = InventoryCleanupVision.inspect_simple_screen(frame)
            self._ensure_cleanup_active(generation)
            if state is None:
                raise RuntimeError(f"{reason}第 {frame_number} 帧未识别到简单整理页面")
            if state.bold_cleanup != BoldCleanupState.OFF:
                raise RuntimeError(
                    f"{reason}第 {frame_number} 帧未确认“大胆整理”处于关闭状态"
                )
            if require_ready and not any(state.selected_categories):
                raise RuntimeError(
                    f"{reason}第 {frame_number} 帧没有绿色的可整理分类"
                )
            if require_ready and not state.execute_enabled:
                raise RuntimeError(
                    f"{reason}第 {frame_number} 帧未确认绿色整理按钮可用"
                )
            last = state
            if frame_number < self.CLEANUP_CONFIRM_FRAMES:
                time.sleep(self.CLEANUP_CONFIRM_INTERVAL_SECONDS)
        if last is None:  # pragma: no cover - 常量至少为 1
            raise RuntimeError("未取得整理页面安全状态")
        return last

    def _ensure_cleanup_active(self, generation: int) -> None:
        if (
            not self._enabled.is_set()
            or self._paused.is_set()
            or generation != self._interrupt_generation
            or self._shutdown.is_set()
        ):
            raise _CleanupCancelled()

    @staticmethod
    def _bottom_center_button(frame: np.ndarray) -> tuple[int, int]:
        height, width = frame.shape[:2]
        return round(width * 0.50), round(height * 0.925)
