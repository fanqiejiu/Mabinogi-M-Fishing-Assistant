"""战斗读条定位 v2：降采样粗扫 + 原图窗口精读 + 锚点确认。

实战帧核对确认：模式一追踪的绿条实际是角色头顶的拉线读条（上方是
鱼竿抛线圆图标、下方是角色名），并非鱼头顶的体力条——但它在功能上
就是战斗状态显示器（鱼挣扎时条被消耗、鱼力竭时恢复），C3 实测中点
灰→绿确认的收鱼全部成功，信号源有效，此处仅做语义修正。

原实现的两个瓶颈及对策：
1. 旧锚点模板带压缩噪点，同物匹配只有 0.66-0.86，被 0.80 阈值误杀
   约半数（接合率 1/3 的直接死因）→ 改用实战帧重裁的干净模板，
   实战分数升到 0.82-1.0。
2. 整帧原分辨率绿色连通域分析约 64ms → 4x 降采样粗扫 + 候选小窗
   精读 + 紧窗锚点确认，实测约 3ms。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..constants import ROD_ICON_ANCHOR_LIVE_PATH

# 粗扫降采样倍率；1080p 下条高约 17px，缩 4 倍后仍有 4px 可检。
_COARSE_FACTOR = 4

# 绿色填充的 HSV 区间（与原实现一致）。
_GREEN_LOWER = np.array([35, 60, 70])
_GREEN_UPPER = np.array([100, 255, 255])

# 原分辨率下的条几何约束（与原实现一致）。
_MIN_WIDTH, _MAX_WIDTH = 24, 480
_MIN_HEIGHT, _MAX_HEIGHT = 5, 32

# 锚点确认阈值：重裁模板后真条实战分数 0.82-1.0（33 根样本）。
DEFAULT_ANCHOR_CONFIDENCE = 0.70

# 读条只会出现在画面中部（角色锁定在画面中央、条在其头顶；镜头 zoom
# 只改变高度不改变这一区间）；角落的 UI 绿条被此硬条件结构性排除。
_CENTER_BAND_Y = (0.08, 0.60)
_CENTER_BAND_X = (0.15, 0.85)

# 锚点模板匹配的搜索尺度（覆盖镜头 zoom 变化；模板已是实战 1080p 裁片）。
_ANCHOR_SCALES = (0.75, 0.90, 1.00, 1.10, 1.25, 1.45)

# 精读窗口在候选四周的外扩量（像素，原分辨率）。
_REFINE_PAD = 12

_anchor_template: np.ndarray | None = None


@dataclass(frozen=True)
class StaminaBarV2:
    """一次成功定位；坐标为整帧像素坐标系。"""

    center: tuple[int, int]
    fill_left: int
    fill_width: int
    fill_height: int
    anchor_confidence: float


def _load_anchor_template() -> np.ndarray | None:
    global _anchor_template
    if _anchor_template is None:
        _anchor_template = cv2.imread(
            str(ROD_ICON_ANCHOR_LIVE_PATH), cv2.IMREAD_COLOR
        )
    return _anchor_template


def _coarse_candidates(frame_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
    """4x 降采样图上找细长绿色区块；返回原分辨率坐标的粗框。"""
    small = cv2.resize(
        frame_bgr,
        None,
        fx=1.0 / _COARSE_FACTOR,
        fy=1.0 / _COARSE_FACTOR,
        interpolation=cv2.INTER_AREA,
    )
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _GREEN_LOWER, _GREEN_UPPER)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    out = []
    for index in range(1, count):
        x, y, width, height, area = (int(value) for value in stats[index])
        if not (
            _MIN_WIDTH // _COARSE_FACTOR <= width <= _MAX_WIDTH // _COARSE_FACTOR
            and max(1, _MIN_HEIGHT // _COARSE_FACTOR)
            <= height
            <= _MAX_HEIGHT // _COARSE_FACTOR
        ):
            continue
        if width < height * 2 or area < width * height * 0.5:
            continue
        out.append(
            (
                x * _COARSE_FACTOR,
                y * _COARSE_FACTOR,
                width * _COARSE_FACTOR,
                height * _COARSE_FACTOR,
            )
        )
    return out


def _refine_candidate(
    frame_bgr: np.ndarray, coarse: tuple[int, int, int, int]
) -> tuple[int, int, int, int] | None:
    """在候选外扩小窗内以原分辨率重找条几何，消除粗扫量化误差。"""
    frame_height, frame_width = frame_bgr.shape[:2]
    x, y, width, height = coarse
    left = max(0, x - _REFINE_PAD)
    top = max(0, y - _REFINE_PAD)
    right = min(frame_width, x + width + _REFINE_PAD)
    bottom = min(frame_height, y + height + _REFINE_PAD)
    window = frame_bgr[top:bottom, left:right]
    if window.size == 0:
        return None
    hsv = cv2.cvtColor(window, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, _GREEN_LOWER, _GREEN_UPPER)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8
    )
    best = None
    for index in range(1, count):
        cx, cy, cw, ch, area = (int(value) for value in stats[index])
        if not (_MIN_WIDTH <= cw <= _MAX_WIDTH and _MIN_HEIGHT <= ch <= _MAX_HEIGHT):
            continue
        if cw < ch * 2 or area < cw * ch * 0.55:
            continue
        if best is None or cw > best[2]:
            best = (left + cx, top + cy, cw, ch)
    return best


def _anchor_confidence(
    frame_bgr: np.ndarray, x: int, y: int, width: int, height: int
) -> float:
    """在条上方搜索中鱼圆形图标；返回多尺度模板匹配最高分。"""
    template = _load_anchor_template()
    if template is None:
        return 0.0
    frame_height, frame_width = frame_bgr.shape[:2]
    # 图标固定在条上方（实测中心约在条左缘 + (60~110, -40~-75)），
    # 紧窗即可覆盖，不需要原实现的 140-420 x 80-240 大窗。
    left = max(0, x - 20)
    right = min(frame_width, x + min(width, 160) + 60)
    top = max(0, y - 120)
    bottom = min(frame_height, y - 4)
    if right - left < 20 or bottom - top < 20:
        return 0.0
    search = frame_bgr[top:bottom, left:right]
    best = 0.0
    for scale in _ANCHOR_SCALES:
        scaled = cv2.resize(template, None, fx=scale, fy=scale)
        if (
            scaled.shape[0] > search.shape[0]
            or scaled.shape[1] > search.shape[1]
        ):
            continue
        result = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(result.max()))
    return best


def find_stamina_bar_v2(
    frame_bgr: np.ndarray,
    last_center: tuple[int, int] | None = None,
    min_anchor_confidence: float = DEFAULT_ANCHOR_CONFIDENCE,
) -> StaminaBarV2 | None:
    """整帧定位角色头顶体力条；未通过锚点确认时返回 None。"""
    if frame_bgr is None or frame_bgr.ndim != 3:
        return None
    frame_height, frame_width = frame_bgr.shape[:2]
    refined_bars: list[tuple[int, int, int, int]] = []
    for coarse in _coarse_candidates(frame_bgr):
        refined = _refine_candidate(frame_bgr, coarse)
        if refined is None:
            continue
        x, y, width, height = refined
        center_x = x + width // 2
        center_y = y + height // 2
        if not (
            _CENTER_BAND_X[0] * frame_width
            <= center_x
            <= _CENTER_BAND_X[1] * frame_width
            and _CENTER_BAND_Y[0] * frame_height
            <= center_y
            <= _CENTER_BAND_Y[1] * frame_height
        ):
            continue
        refined_bars.append(refined)

    # 昂贵的锚点确认按先验排序后执行，首个过阈即接受——阈值型决策
    # 允许提前返回（margin 型比较才禁止早退）。先验：靠近上一次条
    # 位置优先；无历史时靠近画面中央（角色站位）优先。
    reference = (
        last_center
        if last_center is not None
        else (frame_width // 2, int(frame_height * 0.30))
    )
    refined_bars.sort(
        key=lambda bar: float(
            np.hypot(
                bar[0] + bar[2] // 2 - reference[0],
                bar[1] + bar[3] // 2 - reference[1],
            )
        )
    )
    for x, y, width, height in refined_bars:
        confidence = _anchor_confidence(frame_bgr, x, y, width, height)
        if confidence < min_anchor_confidence:
            continue
        return StaminaBarV2(
            center=(x + width // 2, y + height // 2),
            fill_left=x,
            fill_width=width,
            fill_height=height,
            anchor_confidence=confidence,
        )
    return None
