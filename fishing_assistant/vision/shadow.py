"""检测 v2 影子记录器：与现有识别并行运行，只观察不决策。

在引擎识别循环旁路运行 v2 签名链（圆定位 → 签名 → 时间确认），把
v2 判定与引擎判定的对照写入 jsonl；分歧帧限流存盘供离线分析；
上钩转态瞬间采集全帧（垃圾/真鱼咬钩线索的数据来源）。

铁则：影子路径的任何内部异常都不得影响主循环——所有公开方法整体
try/except；图像落盘走后台线程，主循环只付入队成本。
"""

from __future__ import annotations

import json
import queue
import threading
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from .confirm import TemporalConfirmer
from .signature import classify_signature, extract_signature, locate_button_in_roi


class ShadowRecorder:
    """v2 影子判定与对照记录；线程安全由内部锁保证。"""

    MAX_DUMPS_PER_KIND = 3
    MAX_HOOK_CAPTURES = 40

    def __init__(self, output_dir: Path | str) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._dir / "shadow.jsonl"
        self._log_file = open(self._log_path, "a", encoding="utf-8")
        self._confirmer = TemporalConfirmer()
        self._lock = threading.Lock()
        self._dump_counts: Counter[str] = Counter()
        self._hook_captures = 0
        self._write_queue: queue.Queue[tuple[Path, np.ndarray] | None] = queue.Queue(
            maxsize=16
        )
        self._writer = threading.Thread(target=self._drain_writes, daemon=True)
        self._writer.start()
        self._closed = False

    def _drain_writes(self) -> None:
        while True:
            item = self._write_queue.get()
            if item is None:
                return
            path, image = item
            try:
                cv2.imwrite(str(path), image)
            except Exception:
                pass

    def _enqueue_image(self, path: Path, image: np.ndarray) -> None:
        try:
            self._write_queue.put_nowait((path, image.copy()))
        except queue.Full:
            pass

    def record_icon(
        self,
        roi_bgr: np.ndarray | None,
        engine_state: str,
        engine_confidence: float,
        now: float | None = None,
    ) -> None:
        """对一帧 ROI 运行 v2 链并记录与引擎判定的对照。"""
        try:
            timestamp = time.monotonic() if now is None else now
            v2_state = "no-circle"
            v2_confidence = 0.0
            if roi_bgr is not None and getattr(roi_bgr, "ndim", 0) == 3:
                circle = locate_button_in_roi(roi_bgr)
                if circle is not None:
                    cx, cy, radius = circle
                    features = extract_signature(roi_bgr, cx, cy, 2 * radius)
                    v2_state, v2_confidence = classify_signature(features)
            confirm_input = (
                v2_state if v2_state not in ("no-circle",) else "unknown"
            )
            confirmed = self._confirmer.update(confirm_input, timestamp)
            # 引擎的 normal 对应 v2 的「无状态外观」；其余状态名两侧一致。
            agree = (
                v2_state == engine_state
                if engine_state != "normal"
                else v2_state in ("unknown", "no-circle")
            )
            with self._lock:
                if self._closed:
                    return
                self._log_file.write(
                    json.dumps(
                        {
                            "t": round(timestamp, 3),
                            "engine": engine_state,
                            "engine_conf": round(float(engine_confidence), 3),
                            "v2": v2_state,
                            "v2_conf": round(float(v2_confidence), 3),
                            "v2_confirmed": confirmed,
                            "agree": agree,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                if not agree and roi_bgr is not None:
                    kind = f"{engine_state}-vs-{v2_state}"
                    if self._dump_counts[kind] < self.MAX_DUMPS_PER_KIND:
                        self._dump_counts[kind] += 1
                        name = f"diff_{kind}_{timestamp:.1f}.png"
                        self._enqueue_image(self._dir / name, roi_bgr)
        except Exception:
            pass

    def record_hook_transition(
        self, full_frame_bgr: np.ndarray | None, now: float | None = None
    ) -> None:
        """上钩转态瞬间采集全帧（限量），供垃圾/真鱼咬钩差异分析。"""
        try:
            if full_frame_bgr is None or getattr(full_frame_bgr, "ndim", 0) != 3:
                return
            timestamp = time.monotonic() if now is None else now
            with self._lock:
                if self._closed or self._hook_captures >= self.MAX_HOOK_CAPTURES:
                    return
                self._hook_captures += 1
                name = f"hook_{self._hook_captures:03d}_{timestamp:.1f}.png"
            self._enqueue_image(self._dir / name, full_frame_bgr)
        except Exception:
            pass

    def close(self) -> None:
        try:
            with self._lock:
                if self._closed:
                    return
                self._closed = True
            self._write_queue.put(None)
            self._writer.join(timeout=2.0)
            self._log_file.close()
        except Exception:
            pass
