"""比例签名分类：按钮圆内颜色占比 + 结构特征的快速状态判别。

契约：判定"画面呈现哪个状态外观"。转态动画残留判成该状态是正确行为，
滤除短暂外观由上层时间基准确认负责。判别优先 precision（误报会按错键），
recall 缺口由模板仲裁层兜底。

所有区间界值由 E2E 帧库标签样本的实测分布拟定（数据驱动，非手调）：
dryrun1/dryrun2 共 44 张状态帧 + 42 张 normal 帧 + 2 张误触发阴性样本。
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

SIGNATURE_STATES = (
    "waiting_bite",
    "fish_hooked",
    "ready_to_cast",
    "idle_recovery",
)

# 按钮半径相对 ROI 图高的合理区间（160x180 ROI 内实测半径约 75）。
_ROI_MIN_RADIUS_RATIO = 0.28
_ROI_MAX_RADIUS_RATIO = 0.55

# 亮度归一化基准：V 通道 p95 拉回该值，抵消昼夜/阴影明暗差。
_BRIGHTNESS_TARGET = 230.0


@dataclass(frozen=True)
class SignatureFeatures:
    """圆内接正方形 64x64 归一化空间中的颜色占比与结构特征。"""

    green: float
    blue: float
    red: float
    white: float
    dark: float
    bottom_blue: float
    center_white: float
    center_dark: float


# 各状态的 box 判别式：(特征名, 下界, 上界)；上/下界为 None 表示单边。
_STATE_RULES: dict[str, tuple[tuple[str, float | None, float | None], ...]] = {
    "ready_to_cast": (
        ("green", 0.53, 0.73),
        ("blue", 0.18, 0.36),
        ("bottom_blue", 0.42, 0.64),
        ("red", None, 0.04),
        ("dark", None, 0.10),
    ),
    "waiting_bite": (
        ("green", 0.56, 0.80),
        ("blue", None, 0.06),
        ("white", 0.18, 0.42),
        ("red", None, 0.03),
        ("dark", None, 0.10),
        # 白方块填满圆心（真样本全部 1.00）；骑马图标的白是分散的马身
        # （0.54/0.66），此条把 horse 提示隔离给模板仲裁层。
        ("center_white", 0.85, None),
    ),
    "fish_hooked": (
        ("green", 0.45, 0.70),
        ("red", 0.07, 0.22),
        ("white", None, 0.12),
        ("dark", None, 0.10),
    ),
    "idle_recovery": (
        ("center_white", 0.50, 0.85),
        # 指南针放大动画时红指针占比升到 0.09；与 fish_hooked 的混淆由
        # green 条件隔离（hooked 要求 green>=0.45，idle 要求 <0.35）。
        ("red", None, 0.12),
        ("green", None, 0.35),
        # 真指南针中心必有黑点（实测 0.88-1.0）；收鱼奖励动画、读条
        # 浮水印等白色叠加画面该值为 0，是最强的 idle 真伪判别。
        ("center_dark", 0.50, None),
    ),
}

# 分层信心阈值：低于此值的命中一律降为 unknown（交给模板仲裁层）。
# 数据锚点：标签状态帧正判信心最低 0.254，杂合过渡帧误命中信心 0.08 以下。
MIN_SIGNATURE_CONFIDENCE = 0.15


def locate_button_in_roi(roi_bgr: np.ndarray) -> tuple[float, float, float] | None:
    """在 ROI 裁片内定位按钮圆；返回 (cx, cy, r) 或 None。"""
    if roi_bgr is None or roi_bgr.ndim != 3:
        return None
    height = roi_bgr.shape[0]
    gray = cv2.medianBlur(cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY), 5)
    circles = cv2.HoughCircles(
        gray,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=100,
        param1=120,
        param2=30,
        minRadius=int(height * _ROI_MIN_RADIUS_RATIO),
        maxRadius=int(height * _ROI_MAX_RADIUS_RATIO),
    )
    if circles is None:
        return None
    cx, cy, radius = circles[0][0]
    return float(cx), float(cy), float(radius)


def extract_signature(
    bgr: np.ndarray, cx: float, cy: float, diameter: float
) -> SignatureFeatures | None:
    """裁按钮圆内接正方形，归一化到 64x64 后抽取签名特征。"""
    if bgr is None or bgr.ndim != 3 or diameter <= 0:
        return None
    half = int((diameter / 2.0) / 2**0.5)
    if half < 4:
        return None
    top, bottom = int(cy) - half, int(cy) + half
    left, right = int(cx) - half, int(cx) + half
    crop = bgr[max(0, top) : bottom, max(0, left) : right]
    if crop.size == 0:
        return None
    norm = cv2.resize(crop, (64, 64), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(norm, cv2.COLOR_BGR2HSV).astype(np.float64)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    p95 = max(float(np.percentile(val, 95)), 1.0)
    val = np.clip(val * (_BRIGHTNESS_TARGET / p95), 0.0, 255.0)
    total = 64 * 64
    white_mask = (sat < 50) & (val > 170)
    return SignatureFeatures(
        green=float(((hue >= 35) & (hue <= 85) & (sat > 60)).sum() / total),
        blue=float(((hue > 85) & (hue <= 130) & (sat > 60)).sum() / total),
        red=float((((hue < 10) | (hue > 170)) & (sat > 80)).sum() / total),
        white=float(white_mask.sum() / total),
        dark=float((val < 90).sum() / total),
        bottom_blue=float(
            ((hue[32:] > 85) & (hue[32:] <= 130) & (sat[32:] > 60)).sum()
            / (total / 2)
        ),
        center_white=float(white_mask[22:42, 22:42].sum() / 400),
        center_dark=float((val[28:36, 28:36] < 100).sum() / 64),
    )


def _rule_margin(
    features: SignatureFeatures,
    rules: tuple[tuple[str, float | None, float | None], ...],
) -> float:
    """返回判别式的最小相对余裕；任一条件不满足则为 0（不提前退出）。"""
    margins = []
    for name, lower, upper in rules:
        value = getattr(features, name)
        if lower is not None and upper is not None:
            if not lower <= value <= upper:
                margins.append(0.0)
                continue
            half_span = (upper - lower) / 2.0
            margins.append(min(value - lower, upper - value) / max(half_span, 1e-9))
        elif upper is not None:
            if value > upper:
                margins.append(0.0)
                continue
            margins.append((upper - value) / max(upper, 1e-9))
        else:
            if lower is None or value < lower:
                margins.append(0.0)
                continue
            margins.append((value - lower) / max(1.0 - lower, 1e-9))
    return min(margins) if margins else 0.0


def classify_signature(
    features: SignatureFeatures | None,
    min_confidence: float = MIN_SIGNATURE_CONFIDENCE,
) -> tuple[str, float]:
    """返回 (状态, 信心)；无特征、无命中、多重命中或低信心一律 ('unknown', 0.0)。"""
    if features is None:
        return "unknown", 0.0
    hits = []
    for state, rules in _STATE_RULES.items():
        margin = _rule_margin(features, rules)
        if margin > 0.0:
            hits.append((state, margin))
    if len(hits) != 1 or hits[0][1] < min_confidence:
        return "unknown", 0.0
    return hits[0]
