"""时间基准状态确认：以持续时长取代连续帧计数的去抖动。

连续 N 帧计数与轮询节奏绑死——同样的 2 帧在 75ms/帧的快机上是
150ms、在 200ms/帧的弱机上是 400ms，行为随硬件漂移。本确认器只看
"候选状态已持续多久"，节奏无关。unknown 观测不立即清除已确认状态
（容忍模糊帧），持续 clear_seconds 后才清除。
"""

from __future__ import annotations

_UNCONFIRMED = "unknown"


class TemporalConfirmer:
    """把逐帧瞬时观测流折算成时间基准确认的稳定状态。"""

    def __init__(
        self, hold_seconds: float = 0.15, clear_seconds: float = 0.20
    ) -> None:
        self._hold_seconds = float(hold_seconds)
        self._clear_seconds = float(clear_seconds)
        self._confirmed: str | None = None
        self._candidate: str | None = None
        self._candidate_since: float = 0.0
        self._unknown_since: float | None = None

    def reset(self) -> None:
        self._confirmed = None
        self._candidate = None
        self._candidate_since = 0.0
        self._unknown_since = None

    def update(self, observed: str, now: float) -> str | None:
        """喂入一帧观测（状态名或 'unknown'），返回当前已确认状态。"""
        if observed == _UNCONFIRMED:
            self._candidate = None
            if self._confirmed is not None:
                if self._unknown_since is None:
                    self._unknown_since = now
                elif now - self._unknown_since >= self._clear_seconds:
                    self._confirmed = None
                    self._unknown_since = None
            return self._confirmed

        self._unknown_since = None
        if observed == self._confirmed:
            self._candidate = None
            return self._confirmed
        if observed != self._candidate:
            self._candidate = observed
            self._candidate_since = now
            return self._confirmed
        if now - self._candidate_since >= self._hold_seconds:
            self._confirmed = observed
            self._candidate = None
        return self._confirmed
