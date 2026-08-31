"""检测 v2 视觉模块：几何校准、比例签名分类等纯函数组件。

本包只依赖 cv2 / numpy，不依赖 ok-script 与 UI 层，便于离线帧库回归。
"""

from .calibration import (
    REFERENCE_DIAMETER,
    TEMPLATE_SCALE_AT_REFERENCE,
    ButtonCalibration,
    calibrate_button,
    load_button_templates,
)
from .confirm import TemporalConfirmer
from .signature import (
    MIN_SIGNATURE_CONFIDENCE,
    SIGNATURE_STATES,
    SignatureFeatures,
    classify_signature,
    extract_signature,
    locate_button_in_roi,
)
from .stamina import DEFAULT_ANCHOR_CONFIDENCE, StaminaBarV2, find_stamina_bar_v2

__all__ = [
    "REFERENCE_DIAMETER",
    "TEMPLATE_SCALE_AT_REFERENCE",
    "ButtonCalibration",
    "calibrate_button",
    "load_button_templates",
    "TemporalConfirmer",
    "MIN_SIGNATURE_CONFIDENCE",
    "SIGNATURE_STATES",
    "SignatureFeatures",
    "classify_signature",
    "extract_signature",
    "locate_button_in_roi",
    "DEFAULT_ANCHOR_CONFIDENCE",
    "StaminaBarV2",
    "find_stamina_bar_v2",
]
