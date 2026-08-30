import unittest
from unittest.mock import MagicMock, patch

from fishing_assistant.startup_guard import SingleInstanceGuard, prepare_windows_startup


class StartupGuardTests(unittest.TestCase):
    def test_named_mutex_rejects_second_instance(self) -> None:
        guard = SingleInstanceGuard("Local\\test-mabinogi-helper")
        with patch(
            "fishing_assistant.startup_guard.sys.platform", "win32"
        ), patch(
            "fishing_assistant.startup_guard._create_named_mutex",
            return_value=(123, True),
        ), patch(
            "fishing_assistant.startup_guard._close_native_handle"
        ) as close_handle:
            self.assertFalse(guard.acquire())

        close_handle.assert_called_once_with(123)

    def test_named_mutex_is_released_on_close(self) -> None:
        guard = SingleInstanceGuard("Local\\test-mabinogi-helper")
        with patch(
            "fishing_assistant.startup_guard.sys.platform", "win32"
        ), patch(
            "fishing_assistant.startup_guard._create_named_mutex",
            return_value=(456, False),
        ), patch(
            "fishing_assistant.startup_guard._close_native_handle"
        ) as close_handle:
            self.assertTrue(guard.acquire())
            guard.close()
            guard.close()

        close_handle.assert_called_once_with(456)

    def test_non_admin_instance_releases_lock_before_uac_relaunch(self) -> None:
        fake_guard = MagicMock(spec=SingleInstanceGuard)
        fake_guard.acquire.return_value = True
        with patch(
            "fishing_assistant.startup_guard.SingleInstanceGuard",
            return_value=fake_guard,
        ), patch(
            "fishing_assistant.startup_guard.is_running_as_admin",
            return_value=False,
        ), patch(
            "fishing_assistant.startup_guard.relaunch_as_admin",
            return_value=True,
        ) as relaunch, patch(
            "fishing_assistant.startup_guard.show_native_message"
        ) as message:
            result = prepare_windows_startup()

        self.assertIsNone(result)
        fake_guard.close.assert_called_once_with()
        relaunch.assert_called_once_with()
        message.assert_not_called()

    def test_admin_instance_keeps_guard_for_application_lifetime(self) -> None:
        fake_guard = MagicMock(spec=SingleInstanceGuard)
        fake_guard.acquire.return_value = True
        with patch(
            "fishing_assistant.startup_guard.SingleInstanceGuard",
            return_value=fake_guard,
        ), patch(
            "fishing_assistant.startup_guard.is_running_as_admin",
            return_value=True,
        ):
            result = prepare_windows_startup()

        self.assertIs(result, fake_guard)
        fake_guard.close.assert_not_called()

    def test_existing_instance_stops_before_admin_check(self) -> None:
        fake_guard = MagicMock(spec=SingleInstanceGuard)
        fake_guard.acquire.return_value = False
        with patch(
            "fishing_assistant.startup_guard.SingleInstanceGuard",
            return_value=fake_guard,
        ), patch(
            "fishing_assistant.startup_guard.is_running_as_admin"
        ) as admin_check, patch(
            "fishing_assistant.startup_guard.show_native_message"
        ) as message:
            result = prepare_windows_startup()

        self.assertIsNone(result)
        admin_check.assert_not_called()
        message.assert_called_once()
