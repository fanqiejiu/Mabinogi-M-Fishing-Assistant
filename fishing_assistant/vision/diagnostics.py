"""诊断体检：环境事实收集、识别管线分层试跑、诊断快照落盘。

设计契约：
- 诊断层永不抛异常、永不影响识别主路径（所有入口全量防御）。
- 「未命中」是数据不是错误：校准在非钓鱼画面正确拒绝属正常行为，
  输出必须分层敘述，不能压成一个布尔。
- 环境收集依赖 Windows API；读取失败时保留已有捕获事实并记录错误。
"""

from __future__ import annotations

import ctypes
import json
import threading
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

_DPI_SCALE_EPSILON = 0.03
_CAPTURE_SCALE_EPSILON = 0.08
_SNAPSHOT_LOCK = threading.Lock()


def describe_dpi_virtualization(
    unaware_size: tuple[int, int] | None, aware_size: tuple[int, int] | None
) -> dict[str, Any]:
    """对比「进程视角」与「物理」分辨率，判断 DPI 虚拟化是否会缩小截图。"""
    try:
        uw, uh = unaware_size  # type: ignore[misc]
        aw, ah = aware_size  # type: ignore[misc]
        uw, uh, aw, ah = int(uw), int(uh), int(aw), int(ah)
        if min(uw, uh, aw, ah) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return {"virtualized": False, "scale": 1.0, "reason": "invalid input"}
    scale = max(aw / uw, ah / uh)
    return {
        "virtualized": abs(scale - 1.0) > _DPI_SCALE_EPSILON,
        "scale": round(scale, 4),
    }


@dataclass(frozen=True)
class LayerCheck:
    """单层试跑结果；ok=执行没炸，found=该层有命中（未命中≠错误）。"""

    name: str
    ok: bool
    found: bool
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineCheck:
    layers: tuple[LayerCheck, ...]

    def layer(self, name: str) -> LayerCheck | None:
        for item in self.layers:
            if item.name == name:
                return item
        return None

    def as_dict(self) -> list[dict[str, Any]]:
        return [
            {"name": l.name, "ok": l.ok, "found": l.found, "detail": l.detail}
            for l in self.layers
        ]


def _check_calibration(frame: np.ndarray) -> LayerCheck:
    from .calibration import calibrate_button, load_button_templates

    started = time.perf_counter()
    result = calibrate_button(frame, load_button_templates())
    detail: dict[str, Any] = {
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)
    }
    if result is None:
        return LayerCheck("calibration", True, False, detail)
    detail.update(
        center=list(result.center),
        diameter=round(result.diameter, 1),
        scale=round(result.scale, 4),
        confidence=round(result.confidence, 4),
    )
    return LayerCheck("calibration", True, True, detail)


def _check_signature(
    frame: np.ndarray, button_center: tuple[int, int] | None
) -> LayerCheck:
    from ..config import scaled_roi_size
    from . import signature as sig

    if button_center is None:
        return LayerCheck(
            "signature", True, False, {"skipped": "button_center missing"}
        )
    frame_height, frame_width = frame.shape[:2]
    center_x, center_y = (int(value) for value in button_center)
    if not (0 <= center_x < frame_width and 0 <= center_y < frame_height):
        return LayerCheck(
            "signature",
            True,
            False,
            {
                "skipped": "button center outside captured frame",
                "button_center": [center_x, center_y],
                "frame_size": [frame_width, frame_height],
            },
        )
    roi_width, roi_height = scaled_roi_size(frame_width, frame_height)
    left = max(0, min(frame_width - roi_width, center_x - roi_width // 2))
    top = max(0, min(frame_height - roi_height, center_y - roi_height // 2))
    roi = frame[top : top + roi_height, left : left + roi_width]
    detail: dict[str, Any] = {
        "button_center": [center_x, center_y],
        "roi_origin": [left, top],
        "roi_shape": list(roi.shape),
    }
    circle = sig.locate_button_in_roi(roi)
    if circle is None:
        return LayerCheck("signature", True, False, detail)
    circle_x, circle_y, radius = circle
    detail["circle"] = [
        round(circle_x, 1),
        round(circle_y, 1),
        round(radius, 1),
    ]
    features = sig.extract_signature(roi, circle_x, circle_y, 2 * radius)
    if features is not None:
        detail["features"] = {
            key: round(float(value), 4)
            for key, value in asdict(features).items()
        }
    state, confidence = sig.classify_signature(features)
    detail["state"] = state
    detail["confidence"] = round(confidence, 4)
    return LayerCheck("signature", True, state != "unknown", detail)

def _check_stamina(frame: np.ndarray) -> LayerCheck:
    from .stamina import find_stamina_bar_v2

    started = time.perf_counter()
    bar = find_stamina_bar_v2(frame)
    detail: dict[str, Any] = {
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1)
    }
    if bar is None:
        return LayerCheck("stamina", True, False, detail)
    detail["bar"] = {
        key: value
        for key, value in vars(bar).items()
        if isinstance(value, (int, float, tuple, str, bool))
    }
    return LayerCheck("stamina", True, True, detail)


def run_pipeline_check(
    frame_bgr: np.ndarray | None, button_center: tuple[int, int] | None
) -> PipelineCheck:
    """对一帧逐层试跑识别管线；每层独立防御，永不抛异常。"""
    layers: list[LayerCheck] = []
    valid_frame = (
        frame_bgr is not None
        and isinstance(frame_bgr, np.ndarray)
        and frame_bgr.ndim == 3
    )
    checks = (
        ("calibration", lambda f: _check_calibration(f)),
        ("signature", lambda f: _check_signature(f, button_center)),
        ("stamina", lambda f: _check_stamina(f)),
    )
    for name, runner in checks:
        if not valid_frame:
            layers.append(LayerCheck(name, False, False, {"error": "invalid frame"}))
            continue
        try:
            layers.append(runner(frame_bgr))
        except Exception as error:  # 诊断层兜底：任何异常都转成数据
            layers.append(LayerCheck(name, False, False, {"error": repr(error)}))
    return PipelineCheck(tuple(layers))


def describe_capture_scale(
    expected_size: tuple[int, int] | None,
    frame_shape: tuple[int, ...] | None,
) -> dict[str, Any]:
    """比较完整捕获帧与目标尺寸，判断截图是否发生异常缩放。"""
    try:
        expected_width, expected_height = expected_size  # type: ignore[misc]
        frame_height, frame_width = frame_shape[:2]  # type: ignore[index]
        values = tuple(
            int(value)
            for value in (
                expected_width,
                expected_height,
                frame_width,
                frame_height,
            )
        )
        if min(values) <= 0:
            raise ValueError
    except (TypeError, ValueError, IndexError):
        return {"mismatch": False, "reason": "invalid input"}
    expected_width, expected_height, frame_width, frame_height = values
    scale_x = frame_width / expected_width
    scale_y = frame_height / expected_height
    return {
        "mismatch": max(abs(scale_x - 1.0), abs(scale_y - 1.0))
        > _CAPTURE_SCALE_EPSILON,
        "scale_x": round(scale_x, 4),
        "scale_y": round(scale_y, 4),
        "expected_size": [expected_width, expected_height],
        "frame_size": [frame_width, frame_height],
    }


def _physical_resolution(user32: object) -> tuple[int, int] | None:
    """读取主显示器物理模式，不依赖当前进程的 DPI 虚拟化视角。"""

    class DevMode(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", ctypes.c_ushort),
            ("dmDriverVersion", ctypes.c_ushort),
            ("dmSize", ctypes.c_ushort),
            ("dmDriverExtra", ctypes.c_ushort),
            ("dmFields", ctypes.c_ulong),
            ("dmUnion", ctypes.c_byte * 16),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", ctypes.c_wchar * 32),
            ("dmLogPixels", ctypes.c_ushort),
            ("dmBitsPerPel", ctypes.c_ulong),
            ("dmPelsWidth", ctypes.c_ulong),
            ("dmPelsHeight", ctypes.c_ulong),
            ("dmDisplayFlags", ctypes.c_ulong),
            ("dmDisplayFrequency", ctypes.c_ulong),
        ]

    mode = DevMode()
    mode.dmSize = ctypes.sizeof(DevMode)
    if not user32.EnumDisplaySettingsW(None, -1, ctypes.byref(mode)):
        return None
    return int(mode.dmPelsWidth), int(mode.dmPelsHeight)


def collect_environment(
    *,
    frame_shape: tuple[int, ...] | None = None,
    capture_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """收集只读的显示事实；失败时返回部分数据，不影响识别。"""
    capture = dict(capture_info or {})
    environment: dict[str, Any] = {
        "available": True,
        "capture": capture,
        "frame_shape": list(frame_shape) if frame_shape is not None else None,
    }
    try:
        user32 = ctypes.windll.user32
        logical_size = (
            int(user32.GetSystemMetrics(0)),
            int(user32.GetSystemMetrics(1)),
        )
        physical_size = _physical_resolution(user32)
        target_handle = capture.get("target_handle")
        if isinstance(target_handle, int) and target_handle > 0:
            capture["minimized"] = bool(user32.IsIconic(target_handle))
        environment.update(
            logical_resolution=list(logical_size),
            physical_resolution=(
                list(physical_size) if physical_size is not None else None
            ),
            process_dpi_aware=bool(user32.IsProcessDPIAware()),
            dpi=describe_dpi_virtualization(logical_size, physical_size),
        )
    except Exception as error:
        environment["windows_api_error"] = repr(error)
    expected_size = capture.get("expected_size")
    if isinstance(expected_size, (tuple, list)) and len(expected_size) == 2:
        environment["capture_scale"] = describe_capture_scale(
            (int(expected_size[0]), int(expected_size[1])), frame_shape
        )
    return environment


def summarize_environment(
    environment: dict[str, Any],
    frame_shape: tuple[int, ...] | None = None,
) -> list[str]:
    """只警示有直接证据的风险，避免把无边框窗口误报为窗口化。"""
    if not environment or not environment.get("available"):
        return []
    warnings: list[str] = []
    dpi = environment.get("dpi") or {}
    if dpi.get("virtualized"):
        warnings.append(
            f"系统截图可能受到显示缩放影响（约 {dpi.get('scale', 0):.0%}）；"
            "若所有模板同时识别失败，请尝试保持系统缩放与游戏分辨率一致。"
        )
    capture = environment.get("capture") or {}
    capture_scale = environment.get("capture_scale") or {}
    if capture_scale.get("mismatch"):
        warnings.append(
            "实际捕获画面与目标窗口尺寸比例不一致："
            f"目标 {capture_scale.get('expected_size')}，"
            f"截图 {capture_scale.get('frame_size')}。"
        )
    if capture.get("minimized"):
        warnings.append("游戏窗口已最小化，后台截图可能无法取得有效画面。")
    display_mode = capture.get("display_mode") or environment.get("window_mode")
    if display_mode == "windowed":
        warnings.append("当前选择窗口模式；若识别比例不稳定，建议改用无边框全屏。")
    return warnings

def _config_asdict(config_summary: dict[str, Any] | None) -> dict[str, Any]:
    try:
        return dict(config_summary or {})
    except (TypeError, ValueError):
        return {}


def write_snapshot(
    out_dir: Path,
    frame_bgr: np.ndarray | None,
    *,
    reason: str,
    environment: dict[str, Any] | None,
    pipeline: PipelineCheck | None,
    config_summary: dict[str, Any] | None,
) -> Path:
    """把报告和完整捕获帧写入本地 ZIP；不会执行网络请求。"""
    from ..constants import APP_VERSION

    report = {
        "app_version": APP_VERSION,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "reason": reason,
        "environment": environment or {},
        "pipeline": pipeline.as_dict() if pipeline else None,
        "config": _config_asdict(config_summary),
        "frame_shape": list(frame_bgr.shape) if frame_bgr is not None else None,
    }
    with _SNAPSHOT_LOCK:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = out_dir / f"diagnostic-{stamp}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(
                "report.json",
                json.dumps(report, ensure_ascii=False, indent=2, default=str),
            )
            bundle.writestr(
                "README.txt",
                "此诊断包只保存在本机，不会自动上传。\n"
                "frame.png 可能包含角色名或聊天内容，发送前请自行确认。\n",
            )
            if isinstance(frame_bgr, np.ndarray) and frame_bgr.size:
                import cv2

                encoded_ok, encoded = cv2.imencode(".png", frame_bgr[:, :, :3])
                if encoded_ok:
                    bundle.writestr("frame.png", encoded.tobytes())
    return path
