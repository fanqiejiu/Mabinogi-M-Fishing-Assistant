"""GitHub Release 更新检查测试。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from fishing_assistant.updates import check_github_release


class UpdateCheckTests(unittest.TestCase):
    def test_new_release_includes_body_for_popup(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "tag_name": "v0.6.1",
                "html_url": "https://example.invalid/v0.6.1",
                "body": "1. 修复模式二计时。\n2. 优化更新弹窗。",
            },
            ensure_ascii=False,
        ).encode("utf-8")

        with patch("fishing_assistant.updates.urlopen", return_value=response):
            result = check_github_release("owner/repository", "0.6.0")

        self.assertTrue(result.ok)
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "v0.6.1")
        self.assertIn("修复模式二计时", result.release_notes)

    def test_empty_release_body_has_empty_notes(self) -> None:
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {
                "tag_name": "v0.6.0",
                "html_url": "https://example.invalid/v0.6.0",
                "body": None,
            }
        ).encode("utf-8")

        with patch("fishing_assistant.updates.urlopen", return_value=response):
            result = check_github_release("owner/repository", "0.6.0")

        self.assertTrue(result.ok)
        self.assertFalse(result.update_available)
        self.assertEqual(result.release_notes, "")


if __name__ == "__main__":
    unittest.main()