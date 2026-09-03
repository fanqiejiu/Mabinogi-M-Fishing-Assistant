"""背包自动整理所需的 OK 特征定位与安全状态判定。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import cv2
import numpy as np
from ok.feature.FeatureSet import FeatureSet

from .constants import (
    CLEANUP_DETAIL_HEADER_PATH,
    CLEANUP_DONE_TOAST_PATH,
    CLEANUP_RESULT_HEADER_PATH,
    CLEANUP_SIMPLE_HEADER_PATH,
    INVENTORY_TIDY_ANCHOR_PATH,
)


class BoldCleanupState(str, Enum):
    UNKNOWN = "unknown"
    ON = "on"
    OFF = "off"


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    x: int
    y: int
    width: int
    height: int
    confidence: float
    source_scale: float

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.width // 2, self.y + self.height // 2


@dataclass(frozen=True, slots=True)
class SimpleCleanupState:
    anchor: TemplateMatch
    bold_cleanup: BoldCleanupState
    selected_categories: tuple[bool, bool, bool, bool]
    execute_enabled: bool
    category_green_ratios: tuple[float, float, float, float]
    execute_green_ratio: float

    def panel_point(self, x: int, y: int) -> tuple[int, int]:
        # 标题模板在参考面板中的左上角为 (30, 44)。
        return (
            round(self.anchor.x + (x - 30) * self.anchor.source_scale),
            round(self.anchor.y + (y - 44) * self.anchor.source_scale),
        )

    @property
    def toggle_center(self) -> tuple[int, int]:
        return self.panel_point(68, 143)

    @property
    def category_centers(self) -> tuple[tuple[int, int], ...]:
        return (
            self.panel_point(190, 272),
            self.panel_point(505, 272),
            self.panel_point(190, 450),
            self.panel_point(505, 450),
        )

    @property
    def execute_center(self) -> tuple[int, int]:
        return self.panel_point(473, 728)


class InventoryCleanupVision:
    """用 OK FeatureSet 定位整理界面，再用局部颜色核验危险开关。"""

    NORMALIZED_WIDTH = 960
    TEMPLATE_SCALES = (
        0.50,
        0.46,
        0.54,
        0.42,
        0.58,
        0.38,
        0.62,
        0.34,
        0.68,
        0.74,
    )
    INVENTORY_THRESHOLD = 0.72
    SIMPLE_HEADER_THRESHOLD = 0.78
    # “整理对象”与“整理完成”都在画面中部且字体相近，需留出明显余量。
    DETAIL_THRESHOLD = 0.86
    RESULT_THRESHOLD = 0.86
    DONE_THRESHOLD = 0.72

    _feature_set: FeatureSet | None = None
    _templates: dict[Path, np.ndarray | None] = {}

    @classmethod
    def _get_feature_set(cls) -> FeatureSet:
        if cls._feature_set is None:
            cls._feature_set = FeatureSet(
                False,
                "__inventory_cleanup_templates__.json",
                default_horizontal_variance=0,
                default_vertical_variance=0,
                default_threshold=0.80,
            )
        return cls._feature_set

    @classmethod
    def _load_template(cls, path: Path) -> np.ndarray | None:
        if path not in cls._templates:
            cls._templates[path] = cv2.imread(str(path), cv2.IMREAD_COLOR)
        return cls._templates[path]

    @classmethod
    def _find(
        cls,
        bgr: np.ndarray,
        path: Path,
        category: str,
        search: tuple[float, float, float, float],
        threshold: float,
        *,
        gray: bool = True,
    ) -> TemplateMatch | None:
        template = cls._load_template(path)
        if (
            template is None
            or bgr.ndim != 3
            or bgr.shape[0] < 100
            or bgr.shape[1] < 100
        ):
            return None

        frame_height, frame_width = bgr.shape[:2]
        normalized_height = max(
            1, round(frame_height * cls.NORMALIZED_WIDTH / frame_width)
        )
        normalized = cv2.resize(
            bgr[:, :, :3],
            (cls.NORMALIZED_WIDTH, normalized_height),
            interpolation=cv2.INTER_AREA,
        )
        left = max(0, min(cls.NORMALIZED_WIDTH - 1, round(search[0] * cls.NORMALIZED_WIDTH)))
        top = max(0, min(normalized_height - 1, round(search[1] * normalized_height)))
        right = max(left + 1, min(cls.NORMALIZED_WIDTH, round(search[2] * cls.NORMALIZED_WIDTH)))
        bottom = max(top + 1, min(normalized_height, round(search[3] * normalized_height)))
        search_area = normalized[top:bottom, left:right]
        normalized_scale = cls.NORMALIZED_WIDTH / frame_width

        best: TemplateMatch | None = None
        feature_set = cls._get_feature_set()
        for scale in cls.TEMPLATE_SCALES:
            candidate = cv2.resize(
                template,
                (
                    max(1, round(template.shape[1] * scale)),
                    max(1, round(template.shape[0] * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )
            if (
                candidate.shape[0] > search_area.shape[0]
                or candidate.shape[1] > search_area.shape[1]
            ):
                continue
            boxes = feature_set.find_feature(
                search_area,
                category,
                threshold=0.01,
                use_gray_scale=gray,
                template=candidate,
                limit=1,
            )
            if not boxes:
                continue
            box = boxes[0]
            source_scale = scale / normalized_scale
            match = TemplateMatch(
                x=round((left + box.x) / normalized_scale),
                y=round((top + box.y) / normalized_scale),
                width=max(1, round(candidate.shape[1] / normalized_scale)),
                height=max(1, round(candidate.shape[0] / normalized_scale)),
                confidence=float(box.confidence),
                source_scale=source_scale,
            )
            if best is None or match.confidence > best.confidence:
                best = match

        if best is None or best.confidence < threshold:
            return None
        return best

    @classmethod
    def find_inventory_tidy(cls, bgr: np.ndarray) -> TemplateMatch | None:
        return cls._find(
            bgr,
            INVENTORY_TIDY_ANCHOR_PATH,
            "inventory_tidy_anchor",
            (0.70, 0.62, 0.99, 0.94),
            cls.INVENTORY_THRESHOLD,
            gray=False,
        )

    @classmethod
    def find_simple_header(cls, bgr: np.ndarray) -> TemplateMatch | None:
        return cls._find(
            bgr,
            CLEANUP_SIMPLE_HEADER_PATH,
            "cleanup_simple_header",
            (0.12, 0.02, 0.72, 0.62),
            cls.SIMPLE_HEADER_THRESHOLD,
        )

    @classmethod
    def find_detail(cls, bgr: np.ndarray) -> TemplateMatch | None:
        return cls._find(
            bgr,
            CLEANUP_DETAIL_HEADER_PATH,
            "cleanup_detail_header",
            (0.25, 0.14, 0.75, 0.48),
            cls.DETAIL_THRESHOLD,
        )

    @classmethod
    def find_result(cls, bgr: np.ndarray) -> TemplateMatch | None:
        return cls._find(
            bgr,
            CLEANUP_RESULT_HEADER_PATH,
            "cleanup_result_header",
            (0.25, 0.12, 0.75, 0.48),
            cls.RESULT_THRESHOLD,
            gray=False,
        )

    @classmethod
    def find_done_toast(cls, bgr: np.ndarray) -> TemplateMatch | None:
        return cls._find(
            bgr,
            CLEANUP_DONE_TOAST_PATH,
            "cleanup_done_toast",
            (0.20, 0.00, 0.80, 0.24),
            cls.DONE_THRESHOLD,
        )

    @staticmethod
    def _scaled_roi(
        bgr: np.ndarray,
        anchor: TemplateMatch,
        box: tuple[int, int, int, int],
    ) -> np.ndarray | None:
        # box 使用参考面板内坐标；标题模板参考起点为 (30, 44)。
        panel_left = anchor.x - round(30 * anchor.source_scale)
        panel_top = anchor.y - round(44 * anchor.source_scale)
        x1 = panel_left + round(box[0] * anchor.source_scale)
        y1 = panel_top + round(box[1] * anchor.source_scale)
        x2 = panel_left + round(box[2] * anchor.source_scale)
        y2 = panel_top + round(box[3] * anchor.source_scale)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(bgr.shape[1], x2), min(bgr.shape[0], y2)
        if x2 - x1 < 8 or y2 - y1 < 8:
            return None
        return bgr[y1:y2, x1:x2, :3]

    @classmethod
    def inspect_simple_screen(
        cls, bgr: np.ndarray
    ) -> SimpleCleanupState | None:
        anchor = cls.find_simple_header(bgr)
        if anchor is None:
            return None

        toggle_roi = cls._scaled_roi(bgr, anchor, (30, 118, 105, 166))
        category_boxes = (
            (30, 180, 350, 365),
            (345, 180, 665, 365),
            (30, 360, 350, 545),
            (345, 360, 665, 545),
        )
        category_rois = [
            cls._scaled_roi(bgr, anchor, box) for box in category_boxes
        ]
        execute_roi = cls._scaled_roi(bgr, anchor, (280, 675, 665, 780))
        if (
            toggle_roi is None
            or any(roi is None for roi in category_rois)
            or execute_roi is None
        ):
            return None

        toggle_hsv = cv2.cvtColor(toggle_roi, cv2.COLOR_BGR2HSV)
        orange = cv2.inRange(
            toggle_hsv,
            np.array([2, 120, 120]),
            np.array([28, 255, 255]),
        )
        gray = cv2.inRange(
            toggle_hsv,
            np.array([0, 0, 45]),
            np.array([179, 75, 190]),
        )
        orange_ratio = float(np.count_nonzero(orange) / orange.size)
        gray_ratio = float(np.count_nonzero(gray) / gray.size)
        if orange_ratio >= 0.24 and gray_ratio <= 0.12:
            bold_state = BoldCleanupState.ON
        elif gray_ratio >= 0.24 and orange_ratio <= 0.08:
            bold_state = BoldCleanupState.OFF
        else:
            bold_state = BoldCleanupState.UNKNOWN

        category_green_ratios: list[float] = []
        for category_roi in category_rois:
            category_hsv = cv2.cvtColor(category_roi, cv2.COLOR_BGR2HSV)
            category_green = cv2.inRange(
                category_hsv,
                np.array([35, 80, 60]),
                np.array([100, 255, 255]),
            )
            category_green_ratios.append(
                float(
                    np.count_nonzero(category_green)
                    / category_green.size
                )
            )

        execute_hsv = cv2.cvtColor(execute_roi, cv2.COLOR_BGR2HSV)
        execute_green = cv2.inRange(
            execute_hsv,
            np.array([35, 70, 60]),
            np.array([100, 255, 255]),
        )
        execute_green_ratio = float(
            np.count_nonzero(execute_green) / execute_green.size
        )
        return SimpleCleanupState(
            anchor=anchor,
            bold_cleanup=bold_state,
            selected_categories=tuple(
                ratio >= 0.045 for ratio in category_green_ratios
            ),
            execute_enabled=execute_green_ratio >= 0.40,
            category_green_ratios=tuple(category_green_ratios),
            execute_green_ratio=execute_green_ratio,
        )
