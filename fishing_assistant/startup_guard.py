"""Windows 启动前置检查：管理员权限与单实例。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path
import subprocess
import sys

from .constants import APP_NAME


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = r"Local\fanqiejiu.MabinogiMFishingAssistant"


def _create_named_mutex(name: str) -> tuple[int, bool]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    create_mutex.restype = wintypes.HANDLE
    ctypes.set_last_error(0)
    handle = create_mutex(None, False, name)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    return int(handle), ctypes.get_last_error() == ERROR_ALREADY_EXISTS


def _close_native_handle(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    close_handle(handle)


def show_native_message(message: str, *, error: bool = False) -> None:
    """Qt 初始化前也可显示的 Windows 提示框。"""
    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    message_box = user32.MessageBoxW
    message_box.argtypes = (
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.UINT,
    )
    message_box.restype = ctypes.c_int
    icon_flag = 0x00000010 if error else 0x00000040
    message_box(None, message, APP_NAME, 0x00000000 | icon_flag)


def is_running_as_admin() -> bool:
    if sys.platform != "win32":
        return True
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        check_admin = shell32.IsUserAnAdmin
        check_admin.restype = wintypes.BOOL
        return bool(check_admin())
    except OSError:
        return False


def relaunch_as_admin() -> bool:
    """用 UAC 重新启动当前源码入口或已打包 EXE。"""
    if sys.platform != "win32":
        return False
    if getattr(sys, "frozen", False):
        executable = str(Path(sys.executable).resolve())
        arguments = sys.argv[1:]
        working_directory = str(Path(executable).parent)
    else:
        executable = str(Path(sys.executable).resolve())
        arguments = [str(Path(sys.argv[0]).resolve()), *sys.argv[1:]]
        working_directory = str(Path.cwd())
    parameters = subprocess.list2cmdline(arguments)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell_execute = shell32.ShellExecuteW
    shell_execute.argtypes = (
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_int,
    )
    shell_execute.restype = wintypes.HINSTANCE
    result = shell_execute(
        None,
        "runas",
        executable,
        parameters or None,
        working_directory,
        1,
    )
    return int(result) > 32


class SingleInstanceGuard:
    """持有命名互斥体直到主程序退出。"""

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self.name = name
        self._handle: int | None = None

    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        handle, already_exists = _create_named_mutex(self.name)
        if already_exists:
            _close_native_handle(handle)
            return False
        self._handle = handle
        return True

    def close(self) -> None:
        if self._handle is not None:
            _close_native_handle(self._handle)
            self._handle = None


def prepare_windows_startup() -> SingleInstanceGuard | None:
    """先阻止多开；非管理员进程释放互斥体后请求 UAC 重启。"""
    guard = SingleInstanceGuard()
    try:
        acquired = guard.acquire()
    except OSError as error:
        show_native_message(f"无法创建单实例锁，程序未启动。\n\n{error}", error=True)
        return None
    if not acquired:
        show_native_message("程序已经在运行，请勿重复启动。")
        return None
    if is_running_as_admin():
        return guard

    guard.close()
    if not relaunch_as_admin():
        show_native_message("必须允许管理员权限后才能启动。", error=True)
    return None
