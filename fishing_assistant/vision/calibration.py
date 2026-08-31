"""自动校准：在整帧中定位钓鱼按钮圆并推算全局缩放系数。

两层结构：霍夫圆变换给出几何候选（圆心 + 直径），再用状态图标模板
做内容验证——游戏右下角在非钓鱼状态会出现背包等同为圆形的图标，
只看几何会误锁，必须确认"这颗圆确实是钓鱼按钮"。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ..constants import OK_ICON_TEMPLATE_PATHS

# 同一检测管线在 1920x1080 基准帧上量得的按钮直径均值（E2E 112 帧实测）。
# scale 定义为同管线自比，避免"模板量法 vs 实战量法"之间的系统差。
REFERENCE_DIAMETER = 150.6

# 基准直径对应的模板匹配尺度（E2E 尺度收敛值）；
# 下游模板仲裁应使用 calibration.template_scale 而非 scale 本身。
TEMPLATE_SCALE_AT_REFERENCE = 0.98

# 按钮半径相对画面高度的合理区间（1080p 实测半径约 75，比值约 0.069）。
_MIN_RADIUS_RATIO = 0.05
_MAX_RADIUS_RATIO = 0.095

# 校准阶段可能遇到的按钮状态模板（等待咬钩 / 可抛竿 / 上钩 / 指南针）。
_CALIBRATION_TEMPLATE_NAMES = (
    "waiting_bite",
    "fish_hooked",
    "ready_to_cast",
    "idle_recovery",
)

# 各模板的圆几何解释：(模板内圆心 x, y, 模板圆直径, 1080p 实战期望直径)。
# 尺度换算按命中的解释自身进行，不同模板之间不共享参照直径。
# 指南针（idle）状态有内盘与外环两个同心圆特征，霍夫变换可能命中
# 任意一个，因此登记两条解释；外环的模板等效直径按内外径比推算。
_TEMPLATE_INTERPRETATIONS = {
    "waiting_bite": ((67.0, 81.0, 142.2, REFERENCE_DIAMETER),),
    "fish_hooked": ((77.0, 92.0, 141.3, REFERENCE_DIAMETER),),
    "ready_to_cast": ((75.0, 80.0, 142.2, REFERENCE_DIAMETER),),
    "idle_recovery": (
        (102.6, 109.8, 119.9, 128.0),
        (102.6, 109.8, 162.5, 173.5),
    ),
}

_DEFAULT_MIN_CONFIDENCE = 0.6
# 裁片被画面边界截掉超过该比例时该模板不参与验证。
_MAX_CROP_LOSS_RATIO = 0.08


@dataclass(frozen=True)
class ButtonCalibration:
    """一次成功校准的结果；坐标为整帧像素坐标系。"""

    center: tuple[int, int]
    diameter: float
    scale: float
    template_scale: float
    confidence: float


def load_button_templates() -> dict[str, np.ndarray]:
    """加载参与校准的状态图标模板（BGR）。"""
    templates: dict[str, np.ndarray] = {}
    for name in _CALIBRATION_TEMPLATE_NAMES:
        path = OK_ICON_TEMPLATE_PATHS[name]
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            raise FileNotFoundError(f"校准模板缺失或不可读：{path}")
        templates[name] = image
    return templates


def _find_circle_candidates(frame_bgr: np.ndarray) -> list[tuple[int, int, float]]:
    """在右下象限寻找按钮尺寸区间内的圆候选；返回整帧坐标。"""
    height, width = frame_bgr.shape[:2]
    x0, y0 = width // 2, height // 2
    quadrant = frame_bgr[y0:, x0:]
    gray = cv2.cvtColor(quadrant, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    min_radius = int(height * _MIN_RADIUS_RATIO)
    max_radius = int(height * _MAX_RADIUS_RATIO)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(min_radius * 2, 1),
        param1=120,
        param2=40,
        minRadius=min_radius,
        maxRadius=max_radius,
    )
    if circles is None:
        return []
    return [
        (int(round(cx + x0)), int(round(cy + y0)), float(radius))
        for cx, cy, radius in circles[0]
    ]


def _score_candidate(
    frame_bgr: np.ndarray,
    center: tuple[int, int],
    radius: float,
    templates: dict[str, np.ndarray],
) -> tuple[float, float]:
    """以圆心为锚逐条解释裁片比对；返回 (最高相似度, 命中解释的实战参照直径)。"""
    height, width = frame_bgr.shape[:2]
    cx, cy = center
    best_score = -1.0
    best_live_diameter = REFERENCE_DIAMETER
    for name, template in templates.items():
        tpl_h, tpl_w = template.shape[:2]
        for tpl_cx, tpl_cy, tpl_diameter, live_diameter in (
            _TEMPLATE_INTERPRETATIONS.get(name, ())
        ):
            ratio = (2.0 * radius) / tpl_diameter
            left = int(round(cx - tpl_cx * ratio))
            top = int(round(cy - tpl_cy * ratio))
            right = int(round(cx + (tpl_w - tpl_cx) * ratio))
            bottom = int(round(cy + (tpl_h - tpl_cy) * ratio))
            expected_area = (right - left) * (bottom - top)
            clamped = frame_bgr[
                max(0, top) : min(height, bottom), max(0, left) : min(width, right)
            ]
            if expected_area <= 0 or clamped.size == 0:
                continue
            actual_area = clamped.shape[0] * clamped.shape[1]
            if actual_area < expected_area * (1.0 - _MAX_CROP_LOSS_RATIO):
                continue
            resized = cv2.resize(
                clamped, (tpl_w, tpl_h), interpolation=cv2.INTER_AREA
            )
            score = float(
                cv2.matchTemplate(resized, template, cv2.TM_CCOEFF_NORMED)[0][0]
            )
            if score > best_score:
                best_score = score
                best_live_diameter = live_diameter
    return best_score, best_live_diameter


def calibrate_button(
    frame_bgr: np.ndarray,
    templates: dict[str, np.ndarray],
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> ButtonCalibration | None:
    """在整帧中定位钓鱼按钮；无法确认按钮存在时返回 None。"""
    if frame_bgr is None or frame_bgr.ndim != 3:
        return None
    best_result: ButtonCalibration | None = None
    for cx, cy, radius in _find_circle_candidates(frame_bgr):
        confidence, live_diameter = _score_candidate(
            frame_bgr, (cx, cy), radius, templates
        )
        if confidence < min_confidence:
            continue
        diameter = 2.0 * radius
        scale = diameter / live_diameter
        candidate = ButtonCalibration(
            center=(cx, cy),
            diameter=diameter,
            scale=scale,
            template_scale=scale * TEMPLATE_SCALE_AT_REFERENCE,
            confidence=confidence,
        )
        if best_result is None or candidate.confidence > best_result.confidence:
            best_result = candidate
    return best_result
