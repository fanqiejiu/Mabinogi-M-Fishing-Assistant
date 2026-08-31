"""本地错误日志和用户主动分享的诊断包。"""

from __future__ import annotations

import json
import os
import threading
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import APP_DISPLAY_VERSION, APP_NAME
from .system_profile import SystemProfile


_APP_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MabinogiFishingHelper"
LOG_DIR = _APP_DATA_ROOT / "logs"
SUPPORT_DIR = _APP_DATA_ROOT / "support"
VISION_DIAGNOSTICS_DIR = _APP_DATA_ROOT / "vision-diagnostics"
PROFILE_PATH = _APP_DATA_ROOT / "system_profile.json"
_WRITE_LOCK = threading.Lock()
_system_profile: dict[str, str] | None = None


def _log_path() -> Path:
    return LOG_DIR / f"error-{datetime.now():%Y-%m-%d}.jsonl"


def set_system_profile(profile: SystemProfile) -> None:
    """保存本次启动的静态硬件快照，仅写在本地。"""
    global _system_profile
    _system_profile = profile.as_dict()
    _APP_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(
        json.dumps(_system_profile, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_error(
    context: str,
    error: BaseException | str,
    *,
    extra: dict[str, Any] | None = None,
) -> Path | None:
    """追加一条本地错误记录。没有网络请求，也不会上传任何数据。"""
    now = datetime.now().astimezone()
    payload: dict[str, Any] = {
        "timestamp": now.isoformat(timespec="seconds"),
        "application": APP_NAME,
        "version": APP_DISPLAY_VERSION,

        "context": context,
        "error": str(error),
    }
    if isinstance(error, BaseException):
        payload["exception_type"] = type(error).__name__
        payload["traceback"] = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
    if _system_profile is not None:
        payload["system_profile"] = _system_profile
    if extra:
        payload["extra"] = extra

    try:
        with _WRITE_LOCK:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = _log_path()
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, ensure_ascii=False) + "\n")
            return path
    except OSError:
        return None


def create_support_bundle() -> Path:
    """生成可由用户自行发送给作者的 ZIP，不执行上传或网络访问。"""
    SUPPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"MabinogiFishingHelper-diagnostics-{datetime.now():%Y%m%d-%H%M%S}.zip"
    bundle_path = SUPPORT_DIR / filename
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if PROFILE_PATH.exists():
            archive.write(PROFILE_PATH, "system_profile.json")
        if LOG_DIR.exists():
            logs = sorted(LOG_DIR.glob("error-*.jsonl"), reverse=True)[:7]
            for log in logs:
                archive.write(log, f"logs/{log.name}")
        if VISION_DIAGNOSTICS_DIR.exists():
            snapshots = sorted(
                VISION_DIAGNOSTICS_DIR.glob("diagnostic-*.zip"),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )[:3]
            for snapshot in snapshots:
                archive.write(snapshot, f"vision-diagnostics/{snapshot.name}")
        archive.writestr(
            "README.txt",
            "这是本地生成的诊断包，不会由程序自动上传。\n"
            "如需协助，请由用户自行发送给项目维护者。\n"
            "包含：错误日志、启动时读取的一次性硬件信息，以及最近的识别诊断。\n"
            "识别诊断可能包含游戏完整画面；发送前请留意角色名和聊天内容。\n",
        )
    return bundle_path
