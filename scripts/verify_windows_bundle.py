"""Fail a Windows build when foreign native libraries leak into its bundle."""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader


FOREIGN_PATH_MARKERS = (
    "\\codex-runtimes\\",
    "\\poppler\\",
    "\\libheif\\",
    "\\jxrlib\\",
)

FORBIDDEN_ROOT_DLLS = {
    "api-ms-win-core-fibers-l1-1-1.dll",
    "api-ms-win-core-kernel32-legacy-l1-1-1.dll",
    "api-ms-win-core-sysinfo-l1-2-0.dll",
    "icudt78.dll",
    "icuuc.dll",
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
}


def iter_binary_entries(value: object):
    if isinstance(value, (list, tuple)):
        if (
            len(value) == 3
            and isinstance(value[0], str)
            and isinstance(value[1], str)
            and value[2] == "BINARY"
        ):
            yield value[0], value[1]
            return
        for item in value:
            yield from iter_binary_entries(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_binary_entries(item)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    args = parser.parse_args()

    analysis = ast.literal_eval(args.analysis.read_text(encoding="utf-8"))
    foreign_entries = [
        (destination, source)
        for destination, source in iter_binary_entries(analysis)
        if any(marker in source.lower() for marker in FOREIGN_PATH_MARKERS)
    ]

    archive_names = {
        name.replace("/", "\\").lower() for name in CArchiveReader(str(args.exe)).toc
    }
    forbidden_entries = sorted(
        name for name in FORBIDDEN_ROOT_DLLS if name.lower() in archive_names
    )

    errors: list[str] = []
    if foreign_entries:
        errors.append("Foreign native libraries were collected:")
        errors.extend(f"  {destination} <- {source}" for destination, source in foreign_entries)
    if forbidden_entries:
        errors.append("Known incompatible root DLLs were bundled:")
        errors.extend(f"  {name}" for name in forbidden_entries)
    if (
        "pyside6\\qtcore.pyd" not in archive_names
        or "pyside6\\qt6core.dll" not in archive_names
    ):
        errors.append("Required PySide6 QtCore binaries are missing.")

    if errors:
        print("Bundle verification failed.")
        print("\n".join(errors))
        return 1

    print("Bundle verification passed: QtCore present, no foreign DLL contamination found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
