"""可配置的 GitHub Release 更新检查。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class UpdateResult:
    ok: bool
    message: str
    latest_version: str | None = None
    release_url: str | None = None
    update_available: bool = False


def validate_github_repo(repository: str) -> bool:
    return bool(_REPO_PATTERN.fullmatch(repository.strip()))


def _version_key(value: str) -> tuple[int, ...]:
    normalized = value.strip().lower().lstrip("v").split("-", 1)[0]
    parts = normalized.split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"无法识别版本号：{value}")
    return tuple(int(part) for part in parts)


def is_newer_version(latest: str, current: str) -> bool:
    latest_key = _version_key(latest)
    current_key = _version_key(current)
    length = max(len(latest_key), len(current_key))
    return latest_key + (0,) * (length - len(latest_key)) > current_key + (0,) * (
        length - len(current_key)
    )


def check_github_release(repository: str, current_version: str) -> UpdateResult:
    """读取 latest release；仅在用户配置仓库并发起检查时调用。"""
    repository = repository.strip()
    if not validate_github_repo(repository):
        return UpdateResult(False, "请先在设置中填写 GitHub 仓库（格式：owner/repository）。")

    url = f"https://api.github.com/repos/{repository}/releases/latest"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "MabinogiFishingHelper"})
    try:
        with urlopen(request, timeout=8) as response:  # noqa: S310 - fixed GitHub API URL
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 404:
            return UpdateResult(False, "未找到 Latest Release，请确认仓库公开且已创建 Release。")
        return UpdateResult(False, f"GitHub 返回 HTTP {error.code}，请稍后重试。")
    except (URLError, TimeoutError, OSError) as error:
        return UpdateResult(False, f"无法连接 GitHub：{error}")
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return UpdateResult(False, f"无法解析 GitHub 更新信息：{error}")

    tag = str(payload.get("tag_name") or "").strip()
    release_url = str(payload.get("html_url") or "").strip() or None
    if not tag:
        return UpdateResult(False, "Release 未包含 tag_name，无法比较版本。", release_url=release_url)
    try:
        available = is_newer_version(tag, current_version)
    except ValueError:
        return UpdateResult(False, f"Release 版本号“{tag}”格式无法比较。", release_url=release_url)
    if available:
        return UpdateResult(True, f"发现新版本 {tag}，可前往 GitHub 查看。", tag, release_url, True)
    return UpdateResult(True, f"已是最新版本（当前 {current_version}，Release {tag}）。", tag, release_url)
