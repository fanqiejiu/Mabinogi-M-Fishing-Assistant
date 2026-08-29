"""Windows 指定窗口发现、后台截图与定向键盘消息。"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections.abc import Iterable
from ctypes import wintypes
from dataclasses import dataclass

import numpy as np


if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
else:  # pragma: no cover - Windows 桌面工具
    _user32 = None
    _gdi32 = None


WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_ACTIVATE = 0x0006
WM_MOUSEMOVE = 0x0200
WM_MOUSEWHEEL = 0x020A
WA_ACTIVE = 1
SW_RESTORE = 9
PW_RENDERFULLCONTENT = 0x00000002
DIB_RGB_COLORS = 0
BI_RGB = 0
MABINOGI_M_WINDOW_TITLE = "瑪奇 Mobile"


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _RGBQUAD(ctypes.Structure):
    _fields_ = [
        ("rgbBlue", ctypes.c_byte),
        ("rgbGreen", ctypes.c_byte),
        ("rgbRed", ctypes.c_byte),
        ("rgbReserved", ctypes.c_byte),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", _RGBQUAD * 1)]


if _user32 is not None and _gdi32 is not None:
    _user32.GetWindowDC.argtypes = [wintypes.HWND]
    _user32.GetWindowDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _user32.PrintWindow.restype = wintypes.BOOL
    _user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
    _user32.MapVirtualKeyW.restype = wintypes.UINT
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostMessageW.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.BringWindowToTop.restype = wintypes.BOOL
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(_BITMAPINFO),
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.HANDLE,
        wintypes.DWORD,
    ]
    _gdi32.CreateDIBSection.restype = wintypes.HANDLE
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    _gdi32.SelectObject.restype = wintypes.HANDLE
    _gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
    _gdi32.DeleteObject.restype = wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.DeleteDC.restype = wintypes.BOOL

@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x < self.right and self.top <= y < self.bottom


class _OkWindowAdapter:
    """满足 OK WGC/消息交互组件所需的最小窗口适配器，不引入 OK 自带 UI。"""

    def __init__(self, info: WindowInfo, exit_event: threading.Event) -> None:
        self.app_exit_event = exit_event
        self.hwnds: list[tuple[object, ...]] = []
        self.update(info)

    def update(self, info: WindowInfo) -> None:
        self.hwnd = info.handle
        self.top_hwnd = info.handle
        self.x, self.y = info.left, info.top
        self.width, self.height = info.width, info.height
        self.window_width, self.window_height = info.width, info.height
        self.client_width, self.client_height = info.width, info.height
        self.exists = True

    @property
    def capture_target_signature(self) -> tuple[int, int, int, int, int]:
        return self.hwnd, self.width, self.height, self.x, self.y

    def get_abs_cords(self, x: int, y: int) -> tuple[int, int]:
        return self.x + x, self.y + y

    def get_top_window_cords(self, x: int, y: int) -> tuple[int, int]:
        return x, y


class OkWindowBackend:
    """用 ok-script 的 WGC 与 PostMessage 组件提供指定窗口的实验性后台后端。"""

    def __init__(self, info: WindowInfo) -> None:
        self._exit_event = threading.Event()
        self._adapter = _OkWindowAdapter(info, self._exit_event)
        self._capture: object | None = None
        self._interaction: object | None = None
        self._handle = info.handle
        self._lock = threading.RLock()

    @property
    def handle(self) -> int:
        return self._handle

    @staticmethod
    def available() -> bool:
        try:
            from ok.device.capture_methods import WindowsGraphicsCaptureMethod  # noqa: F401
            from ok.device.interaction_methods import PostMessageInteraction  # noqa: F401
        except ImportError:
            return False
        return True

    def update(self, info: WindowInfo) -> None:
        if info.handle != self._handle:
            raise RuntimeError("OK 后台会话的目标窗口已变化，请重新建立连接。")
        with self._lock:
            self._adapter.update(info)

    def _ensure_started(self) -> None:
        if self._capture is not None and self._interaction is not None:
            return
        try:
            from ok.device.capture_methods import WindowsGraphicsCaptureMethod
            from ok.device.interaction_methods import PostMessageInteraction
        except ImportError as error:
            raise RuntimeError(
                "OK 后台组件未安装；请运行 setup.bat 重新安装环境。"
            ) from error
        capture = WindowsGraphicsCaptureMethod(self._adapter)
        self._capture = capture
        self._interaction = PostMessageInteraction(capture, self._adapter)

    def _get_frame_with_warmup(self) -> np.ndarray:
        """WGC 建立会话后的首帧可能稍晚到达，短暂重试而非立刻暂停监测。"""
        for _attempt in range(10):
            frame = self._capture.get_frame()  # type: ignore[union-attr]
            if isinstance(frame, np.ndarray) and frame.ndim == 3 and frame.size:
                return frame
            time.sleep(0.06)
        raise RuntimeError("OK WGC 预热后仍未收到窗口画面，请确认游戏未最小化。")

    def capture_region(
        self,
        info: WindowInfo,
        center_offset: tuple[int, int],
        width: int,
        height: int,
    ) -> np.ndarray:
        self.update(info)
        with self._lock:
            self._ensure_started()
            frame = self._get_frame_with_warmup()
        return _crop_backend_frame(frame, info, center_offset, width, height)

    def capture_frame(self, info: WindowInfo) -> np.ndarray:
        """返回完整 WGC 画面，用于在上钩期间寻找动态体力条。"""
        self.update(info)
        with self._lock:
            self._ensure_started()
            frame = self._get_frame_with_warmup()
        return frame.copy()

    def tap_key(self, key: str, hold_ms: int = 0) -> None:
        with self._lock:
            self._ensure_started()
            self._interaction.send_key(  # type: ignore[union-attr]
                key, max(0.01, hold_ms / 1000)
            )

    def keep_hover(self, info: WindowInfo, center_offset: tuple[int, int]) -> None:
        """仅向目标窗口投递虚拟鼠标移动，不改变系统真实光标。"""
        self.update(info)
        with self._lock:
            self._ensure_started()
            self._interaction.move(*center_offset)  # type: ignore[union-attr]

    def close(self) -> None:
        self._exit_event.set()
        with self._lock:
            if self._capture is not None:
                try:
                    self._capture.close()  # type: ignore[union-attr]
                finally:
                    self._capture = None
            self._interaction = None


def _crop_backend_frame(
    frame: np.ndarray,
    info: WindowInfo,
    center_offset: tuple[int, int],
    width: int,
    height: int,
) -> np.ndarray:
    """按校准时的窗口坐标裁剪 WGC 帧，并兼容 DWM 边框造成的尺寸差。"""
    if frame.ndim != 3 or frame.shape[0] <= 0 or frame.shape[1] <= 0:
        raise RuntimeError("OK WGC 返回了无效画面。")
    frame_height, frame_width = frame.shape[:2]
    scale_x = frame_width / max(1, info.width)
    scale_y = frame_height / max(1, info.height)
    center_x = round(center_offset[0] * scale_x)
    center_y = round(center_offset[1] * scale_y)
    crop_width = max(1, round(width * scale_x))
    crop_height = max(1, round(height * scale_y))
    left, top = center_x - crop_width // 2, center_y - crop_height // 2
    right, bottom = left + crop_width, top + crop_height
    if left < 0 or top < 0 or right > frame_width or bottom > frame_height:
        raise RuntimeError("识别区域已超出 OK WGC 窗口画面，请重新校准。")
    return frame[top:bottom, left:right].copy()


def find_mabinogi_mobile_window(
    windows: Iterable[WindowInfo],
) -> WindowInfo | None:
    """优先寻找标题为“瑪奇 Mobile”的窗口，也兼容附带后缀的标题。"""
    candidates = list(windows)
    expected = MABINOGI_M_WINDOW_TITLE.casefold()
    for item in candidates:
        if item.title.strip().casefold() == expected:
            return item
    return next((item for item in candidates if expected in item.title.casefold()), None)


def _require_windows() -> None:
    if _user32 is None or _gdi32 is None:
        raise RuntimeError("指定窗口模式仅支持 Windows。")


def get_window_info(handle: int) -> WindowInfo | None:
    """返回一个可见顶级窗口的信息；失效的句柄返回 None。"""
    _require_windows()
    if not handle or not _user32.IsWindow(wintypes.HWND(handle)):
        return None
    if not _user32.IsWindowVisible(wintypes.HWND(handle)):
        return None
    if _user32.IsIconic(wintypes.HWND(handle)):
        return None
    title_length = _user32.GetWindowTextLengthW(wintypes.HWND(handle))
    if title_length <= 0:
        return None
    title_buffer = ctypes.create_unicode_buffer(title_length + 1)
    _user32.GetWindowTextW(wintypes.HWND(handle), title_buffer, len(title_buffer))
    rect = wintypes.RECT()
    if not _user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect)):
        return None
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if width < 80 or height < 80:
        return None
    return WindowInfo(handle, title_buffer.value, rect.left, rect.top, width, height)


def list_target_windows() -> list[WindowInfo]:
    """枚举可由用户选择的可见顶级窗口。"""
    _require_windows()
    windows: list[WindowInfo] = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(handle: wintypes.HWND, _parameter: wintypes.LPARAM) -> bool:
        info = get_window_info(int(handle))
        if info is not None:
            windows.append(info)
        return True

    if not _user32.EnumWindows(callback, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return sorted(windows, key=lambda item: item.title.casefold())


def resolve_window(handle: int, title: str) -> WindowInfo | None:
    """优先使用保存的句柄；重启后按完全相同的窗口标题恢复。"""
    info = get_window_info(handle)
    if info is not None and (not title or info.title == title):
        return info
    if not title:
        return None
    matches = [item for item in list_target_windows() if item.title == title]
    return matches[0] if len(matches) == 1 else None


def capture_window_frame(handle: int) -> np.ndarray:
    """以 PrintWindow 捕捉完整目标窗口，供动态体力条识别使用。"""
    _require_windows()
    info = get_window_info(handle)
    if info is None:
        raise RuntimeError("目标窗口不存在、已隐藏或已关闭。")
    return _capture_window_bgra(info)

def capture_window_region(
    handle: int,
    center_offset: tuple[int, int],
    width: int,
    height: int,
) -> np.ndarray:
    """以 PrintWindow 捕捉指定窗口的 BGRA 区域，不读取当前前台窗口。"""
    _require_windows()
    info = get_window_info(handle)
    if info is None:
        raise RuntimeError("目标窗口不存在、已隐藏或已关闭。")
    bitmap = _capture_window_bgra(info)
    center_x, center_y = center_offset
    left = int(center_x - width // 2)
    top = int(center_y - height // 2)
    right, bottom = left + width, top + height
    if left < 0 or top < 0 or right > info.width or bottom > info.height:
        raise RuntimeError("识别区域已超出目标窗口，请重新校准。")
    return bitmap[top:bottom, left:right].copy()


def _capture_window_bgra(info: WindowInfo) -> np.ndarray:
    _require_windows()
    hwnd = wintypes.HWND(info.handle)
    screen_dc = _user32.GetWindowDC(hwnd)
    if not screen_dc:
        raise ctypes.WinError(ctypes.get_last_error())
    memory_dc = _gdi32.CreateCompatibleDC(screen_dc)
    if not memory_dc:
        _user32.ReleaseDC(hwnd, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())

    bits = ctypes.c_void_p()
    bitmap_info = _BITMAPINFO()
    bitmap_info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bitmap_info.bmiHeader.biWidth = info.width
    bitmap_info.bmiHeader.biHeight = -info.height  # Top-down BGRA buffer.
    bitmap_info.bmiHeader.biPlanes = 1
    bitmap_info.bmiHeader.biBitCount = 32
    bitmap_info.bmiHeader.biCompression = BI_RGB
    bitmap = _gdi32.CreateDIBSection(
        memory_dc, ctypes.byref(bitmap_info), DIB_RGB_COLORS, ctypes.byref(bits), None, 0
    )
    if not bitmap:
        _gdi32.DeleteDC(memory_dc)
        _user32.ReleaseDC(hwnd, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())
    previous_bitmap = _gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not _user32.PrintWindow(hwnd, memory_dc, PW_RENDERFULLCONTENT):
            raise RuntimeError("目标窗口不支持后台截图（PrintWindow 失败）。")
        size = info.width * info.height * 4
        buffer_type = ctypes.c_ubyte * size
        buffer = buffer_type.from_address(bits.value)
        return np.ctypeslib.as_array(buffer).reshape((info.height, info.width, 4)).copy()
    finally:
        _gdi32.SelectObject(memory_dc, previous_bitmap)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(memory_dc)
        _user32.ReleaseDC(hwnd, screen_dc)


def activate_window(handle: int) -> WindowInfo:
    """将目标窗口短暂切到前台，用于游戏只接受真实鼠标滚轮的场景。"""
    _require_windows()
    info = get_window_info(handle)
    if info is None:
        raise RuntimeError("目标窗口已关闭或不可见，无法切换到前台。")
    hwnd = wintypes.HWND(info.handle)
    if _user32.IsIconic(hwnd):
        _user32.ShowWindow(hwnd, SW_RESTORE)
    _user32.BringWindowToTop(hwnd)
    if not _user32.SetForegroundWindow(hwnd):
        raise RuntimeError("Windows 未允许切换目标窗口到前台。")
    return info


def post_mouse_wheel(handle: int, steps: int) -> None:
    """向目标窗口投递向上/向下滚轮消息，不影响当前前台窗口。"""
    _require_windows()
    info = get_window_info(handle)
    if info is None:
        raise RuntimeError("目标窗口已关闭或不可见，未发送滚轮消息。")
    if steps == 0:
        return
    hwnd = wintypes.HWND(info.handle)
    if not _user32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    direction = 1 if steps > 0 else -1
    wheel_wparam = ((direction * 120) & 0xFFFF) << 16
    # WM_MOUSEWHEEL 的 lParam 使用屏幕坐标；投到窗口中心可兼容会检查鼠标位置的客户端。
    center_x = info.left + info.width // 2
    center_y = info.top + info.height // 2
    wheel_lparam = ((center_y & 0xFFFF) << 16) | (center_x & 0xFFFF)
    for _ in range(abs(steps)):
        if not _user32.PostMessageW(hwnd, WM_MOUSEWHEEL, wheel_wparam, wheel_lparam):
            raise ctypes.WinError(ctypes.get_last_error())
        time.sleep(0.04)


def post_mouse_move(handle: int, center_offset: tuple[int, int]) -> None:
    """在目标窗口内维持虚拟悬停，不移动用户正在使用的真实鼠标。"""
    _require_windows()
    info = get_window_info(handle)
    if info is None:
        raise RuntimeError("目标窗口已关闭或不可见，无法维持后台悬停。")
    x = min(max(0, int(center_offset[0])), max(0, info.width - 1))
    y = min(max(0, int(center_offset[1])), max(0, info.height - 1))
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    if not _user32.PostMessageW(wintypes.HWND(info.handle), WM_MOUSEMOVE, 0, lparam):
        raise ctypes.WinError(ctypes.get_last_error())


def post_key_tap(
    handle: int, key: str, hold_ms: int = 0, *, activate_message: bool = False
) -> None:
    """仅向目标窗口投递键盘消息，不影响当前前台应用。"""
    _require_windows()
    virtual_key = {"space": 0x20, "w": 0x57, "s": 0x53}.get(key.lower())
    if virtual_key is None:
        raise ValueError(f"不支持的定向按键：{key}")
    if get_window_info(handle) is None:
        raise RuntimeError("目标窗口已关闭或不可见，未发送按键。")
    scan_code = _user32.MapVirtualKeyW(virtual_key, 0)
    down_lparam = 1 | (scan_code << 16)
    up_lparam = down_lparam | (1 << 30) | (1 << 31)
    hwnd = wintypes.HWND(handle)
    if activate_message and not _user32.PostMessageW(hwnd, WM_ACTIVATE, WA_ACTIVE, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    if not _user32.PostMessageW(hwnd, WM_KEYDOWN, virtual_key, down_lparam):
        raise ctypes.WinError(ctypes.get_last_error())
    if hold_ms:
        time.sleep(hold_ms / 1000)
    if not _user32.PostMessageW(hwnd, WM_KEYUP, virtual_key, up_lparam):
        raise ctypes.WinError(ctypes.get_last_error())
