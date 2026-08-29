"""一次性读取本机基础硬件信息；不持续监测、不采集游戏数据。"""

from __future__ import annotations

import platform
import subprocess
import sys
from dataclasses import dataclass, asdict


@dataclass(frozen=True, slots=True)
class SystemProfile:
    cpu: str
    gpu: str
    memory: str
    operating_system: str
    python: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _powershell_lines(script: str) -> list[str]:
    """用 CIM 读取 Windows 硬件名称，失败时交由调用方使用降级信息。"""
    if sys.platform != "win32":
        return []
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def collect_system_profile() -> SystemProfile:
    """返回启动时的静态硬件快照，用于用户主动分享的错误日志。"""
    cpu_lines = _powershell_lines(
        "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"
    )
    gpu_lines = _powershell_lines(
        "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name"
    )
    memory_lines = _powershell_lines(
        "Get-CimInstance Win32_PhysicalMemory | ForEach-Object { "
        "$part = $_.PartNumber.Trim(); "
        "'{0} {1} · {2} GB' -f $_.Manufacturer, $part, "
        "[math]::Round($_.Capacity / 1GB) }"
    )

    processor = platform.processor().strip() or platform.machine() or "未能读取"
    return SystemProfile(
        cpu=" / ".join(cpu_lines) if cpu_lines else processor,
        gpu=" / ".join(gpu_lines) if gpu_lines else "未能读取",
        memory=" / ".join(memory_lines) if memory_lines else "未能读取",
        operating_system=f"{platform.system()} {platform.release()}".strip(),
        python=platform.python_version(),
    )
