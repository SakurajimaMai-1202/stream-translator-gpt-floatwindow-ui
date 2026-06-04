from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import threading
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


APP_NAME = "Remote Subtitle Window"
SETTINGS_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
SETTINGS_FILE = SETTINGS_DIR / "settings.json"

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
gdiplus = ctypes.windll.gdiplus
kernel32 = ctypes.windll.kernel32

WM_DESTROY = 0x0002
WM_NCHITTEST = 0x0084
WM_LBUTTONUP = 0x0202
WM_KEYDOWN = 0x0100
WM_TIMER = 0x0113
WM_APP_EVENT = 0x8001
WM_CLOSE = 0x0010
WM_SIZE = 0x0005
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0
AC_SRC_ALPHA = 1
HTCAPTION = 2
HTBOTTOMRIGHT = 17
HTCLIENT = 1
VK_F2 = 0x71


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_byte),
        ("BlendFlags", ctypes.c_byte),
        ("SourceConstantAlpha", ctypes.c_byte),
        ("AlphaFormat", ctypes.c_byte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_ushort),
        ("biBitCount", ctypes.c_ushort),
        ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", ctypes.c_void_p),
        ("hIcon", ctypes.c_void_p),
        ("hCursor", ctypes.c_void_p),
        ("hbrBackground", ctypes.c_void_p),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint32),
        ("pt", POINT),
    ]


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", ctypes.c_int),
        ("SuppressExternalCodecs", ctypes.c_int),
    ]


class RectF(ctypes.Structure):
    _fields_ = [("X", ctypes.c_float), ("Y", ctypes.c_float), ("Width", ctypes.c_float), ("Height", ctypes.c_float)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASS)]
user32.CreateWindowExW.argtypes = [
    ctypes.c_uint32,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_uint32,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
user32.CreateWindowExW.restype = ctypes.c_void_p
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
user32.ScreenToClient.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.SetTimer.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint, ctypes.c_void_p]
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
user32.UpdateLayeredWindow.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    ctypes.c_void_p,
    ctypes.POINTER(POINT),
    ctypes.c_uint32,
    ctypes.POINTER(BLENDFUNCTION),
    ctypes.c_uint32,
]
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_uint32]
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p

gdiplus.GdiplusStartup.argtypes = [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(GdiplusStartupInput), ctypes.c_void_p]
gdiplus.GdiplusShutdown.argtypes = [ctypes.c_size_t]
gdiplus.GdipCreateFromHDC.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdiplus.GdipSetTextRenderingHint.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipCreateSolidFill.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteBrush.argtypes = [ctypes.c_void_p]
gdiplus.GdipFillRectangleI.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdiplus.GdipCreatePath.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeletePath.argtypes = [ctypes.c_void_p]
gdiplus.GdipAddPathArc.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipAddPathLine.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
gdiplus.GdipClosePathFigure.argtypes = [ctypes.c_void_p]
gdiplus.GdipFillPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipCreateFontFamilyFromName.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteFontFamily.argtypes = [ctypes.c_void_p]
gdiplus.GdipCreateFont.argtypes = [ctypes.c_void_p, ctypes.c_float, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeleteFont.argtypes = [ctypes.c_void_p]
gdiplus.GdipCreateStringFormat.argtypes = [ctypes.c_int, ctypes.c_ushort, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipStringFormatGetGenericTypographic.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipSetStringFormatFlags.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetStringFormatAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipSetStringFormatLineAlign.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipDeleteStringFormat.argtypes = [ctypes.c_void_p]
gdiplus.GdipDrawString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.POINTER(RectF),
    ctypes.c_void_p,
    ctypes.c_void_p,
]
gdiplus.GdipMeasureString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.POINTER(RectF),
    ctypes.c_void_p,
    ctypes.POINTER(RectF),
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_int),
]

gdiplus.GdipSetSmoothingMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
gdiplus.GdipAddPathString.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_float,
    ctypes.POINTER(RectF),
    ctypes.c_void_p,
]
gdiplus.GdipCreatePen1.argtypes = [ctypes.c_uint32, ctypes.c_float, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
gdiplus.GdipDeletePen.argtypes = [ctypes.c_void_p]
gdiplus.GdipDrawPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
gdiplus.GdipSetPenLineJoin.argtypes = [ctypes.c_void_p, ctypes.c_int]


@dataclass
class Settings:
    server: str = "http://127.0.0.1:8765"
    font_size: int = 28
    max_items: int = 3
    show_original: bool = True
    show_translated: bool = True
    show_status: bool = True
    always_on_top: bool = True
    opacity: float = 0.82
    original_color: str = "#55ffff"
    translated_color: str = "#ffdd00"
    background_color: str = "#050505"
    width: int = 760
    height: int = 260
    x: int = 120
    y: int = 120


def normalize_server(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return f"http://{raw}"


def load_settings() -> Settings:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        fields = {field.name for field in Settings.__dataclass_fields__.values()}
        return Settings(**{key: value for key, value in data.items() if key in fields})
    except Exception:
        return Settings()


def save_settings(settings: Settings) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_json(url: str, timeout: float = 4.0) -> dict[str, Any]:
    req = Request(url, headers={"Accept": "application/json", "User-Agent": APP_NAME})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    raw = (hex_color or "#000000").lstrip("#")
    if len(raw) != 6:
        return 0, 0, 0
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def argb(alpha: int, hex_color: str) -> int:
    r, g, b = hex_to_rgb(hex_color)
    return ((max(0, min(255, alpha)) & 0xFF) << 24) | (r << 16) | (g << 8) | b


class SubtitleClient(threading.Thread):
    def __init__(self, settings: Settings, events: queue.Queue[tuple[str, Any]], stop: threading.Event):
        super().__init__(daemon=True)
        self.settings = settings
        self.events = events
        self.stop = stop

    def run(self) -> None:
        while not self.stop.is_set():
            server = normalize_server(self.settings.server)
            if not server:
                self.events.put(("status", ("waiting", "請設定字幕分享網址")))
                self._sleep(2.0)
                continue
            try:
                task_id = self._get_active_task(server)
                if not task_id:
                    self.events.put(("status", ("waiting", f"等待翻譯任務：{server}")))
                    self._sleep(2.5)
                    continue
                self.events.put(("status", ("connected", "已連線，接收字幕中")))
                self._stream(server, task_id)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                self.events.put(("status", ("error", f"連線失敗：{exc}")))
                self._sleep(3.0)
            except Exception as exc:
                self.events.put(("status", ("error", f"字幕串流錯誤：{exc}")))
                self._sleep(3.0)

    def _get_active_task(self, server: str) -> str:
        data = fetch_json(f"{server}/api/translation/active-task")
        return str(data.get("task_id") or "") if data.get("success") else ""

    def _stream(self, server: str, task_id: str) -> None:
        url = f"{server}/api/translation/stream/{quote(task_id, safe='')}"
        req = Request(url, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache", "User-Agent": APP_NAME})
        with urlopen(req, timeout=12) as response:
            event_name = "message"
            data_lines: list[str] = []
            while not self.stop.is_set():
                raw = response.readline()
                if raw == b"":
                    raise ConnectionError("stream closed")
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith(":"):
                    continue
                if line == "":
                    self._dispatch_event(event_name, "\n".join(data_lines))
                    event_name = "message"
                    data_lines = []
                elif line.startswith("event:"):
                    event_name = line[6:].strip() or "message"
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())

    def _dispatch_event(self, event_name: str, payload: str) -> None:
        if not payload:
            return
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return
        if event_name == "subtitle":
            self.events.put(("subtitle", data))
        elif event_name == "status":
            status = str(data.get("status") or "")
            if status in {"completed", "error"}:
                self.events.put(("status", ("waiting", "任務結束，等待下一個任務")))
                raise ConnectionError("task finished")
            self.events.put(("status", ("connected", str(data.get("message") or "翻譯狀態更新"))))
        elif event_name == "error":
            self.events.put(("status", ("error", str(data.get("message") or "字幕串流錯誤"))))

    def _sleep(self, seconds: float) -> None:
        self.stop.wait(seconds)


class LayeredSubtitleWindow:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop = threading.Event()
        self.client: SubtitleClient | None = None
        self.subtitles: list[dict[str, str]] = []
        self.status_type = "waiting"
        self.status_text = "初始化中..."
        self.compact = False
        self.mouse_over = False
        self.hwnd: int | None = None
        self._wndproc = WNDPROC(self._window_proc)
        self._gdiplus_token = ctypes.c_size_t()
        self._start_gdiplus()

    def run(self) -> None:
        self._register_class()
        ex_style = WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if self.settings.always_on_top:
            ex_style |= WS_EX_TOPMOST
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            APP_NAME,
            APP_NAME,
            WS_POPUP,
            self.settings.x,
            self.settings.y,
            self.settings.width,
            self.settings.height,
            None,
            None,
            kernel32.GetModuleHandleW(None),
            None,
        )
        if not self.hwnd:
            raise ctypes.WinError()

        user32.ShowWindow(self.hwnd, 1)
        user32.SetTimer(self.hwnd, 1, 80, None)
        self._start_client()
        self.render()

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self.stop.set()
        save_settings(self.settings)
        gdiplus.GdiplusShutdown(self._gdiplus_token)

    def _start_gdiplus(self) -> None:
        startup_input = GdiplusStartupInput(1, None, 0, 0)
        status = gdiplus.GdiplusStartup(ctypes.byref(self._gdiplus_token), ctypes.byref(startup_input), None)
        if status != 0:
            raise RuntimeError(f"GDI+ startup failed: {status}")

    def _register_class(self) -> None:
        wc = WNDCLASS()
        wc.lpfnWndProc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        wc.hInstance = kernel32.GetModuleHandleW(None)
        wc.hCursor = user32.LoadCursorW(None, 32512)
        wc.lpszClassName = APP_NAME
        user32.RegisterClassW(ctypes.byref(wc))

    def _window_proc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        if msg == WM_CLOSE:
            self._remember_geometry()
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_SIZE:
            self._remember_geometry()
            self.render()
            return 0
        if msg == WM_TIMER or msg == WM_APP_EVENT:
            self._drain_events()
            return 0
        if msg == WM_NCHITTEST:
            x, y = self._client_point_from_lparam(lparam)
            if x >= self.settings.width - 22 and y >= self.settings.height - 22:
                return HTBOTTOMRIGHT
            if self._hit_button(x, y):
                return HTCLIENT
            return HTCAPTION
        if msg == WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            self._click(x, y)
            return 0
        if msg == WM_KEYDOWN and wparam == VK_F2:
            self._open_settings()
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _client_point_from_lparam(self, lparam: int) -> tuple[int, int]:
        point = POINT(ctypes.c_short(lparam & 0xFFFF).value, ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        user32.ScreenToClient(self.hwnd, ctypes.byref(point))
        return point.x, point.y

    def _button_rects(self) -> list[tuple[str, int, int, int, int]]:
        w = self.settings.width
        top = 12
        size = 24
        gap = 11
        left = w - 32
        return [
            ("settings", left, top, left + size, top + size),
            ("compact", left, top + size + gap, left + size, top + size * 2 + gap),
            ("close", left, top + (size + gap) * 2, left + size, top + size * 3 + gap * 2),
        ]

    def _hit_button(self, x: int, y: int) -> bool:
        return any(left <= x <= right and top <= y <= bottom for _, left, top, right, bottom in self._button_rects())

    def _click(self, x: int, y: int) -> None:
        for name, left, top, right, bottom in self._button_rects():
            if left <= x <= right and top <= y <= bottom:
                if name == "settings":
                    self._open_settings()
                elif name == "compact":
                    self.compact = not self.compact
                    self.render()
                elif name == "close":
                    user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
                return

    def _remember_geometry(self) -> None:
        rect = RECT()
        if self.hwnd and user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            self.settings.x = rect.left
            self.settings.y = rect.top
            self.settings.width = max(420, rect.right - rect.left)
            self.settings.height = max(130, rect.bottom - rect.top)

    def _start_client(self) -> None:
        self.stop.set()
        if self.client and self.client.is_alive():
            self.client.join(timeout=0.2)
        self.stop = threading.Event()
        self.client = SubtitleClient(self.settings, self.events, self.stop)
        self.client.start()

    def _check_mouse_over(self) -> bool:
        if not self.hwnd:
            return False
        rect = RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return False
        cursor_pos = POINT()
        if not user32.GetCursorPos(ctypes.byref(cursor_pos)):
            return False
        return (rect.left <= cursor_pos.x <= rect.right and 
                rect.top <= cursor_pos.y <= rect.bottom)

    def _drain_events(self) -> None:
        changed = False
        while True:
            try:
                event_type, data = self.events.get_nowait()
            except queue.Empty:
                break
            changed = True
            if event_type == "status":
                self.status_type, self.status_text = data
            elif event_type == "subtitle":
                self._add_or_update_subtitle(data)
        self._remember_geometry()
        
        # Check if hover state changed
        prev_hover = getattr(self, "mouse_over", False)
        current_hover = self._check_mouse_over()
        self.mouse_over = current_hover
        if current_hover != prev_hover:
            changed = True
            
        if changed:
            self.render()

    def _add_or_update_subtitle(self, data: dict[str, Any]) -> None:
        original = str(data.get("original") or "")
        translated = str(data.get("translated") or "")
        if not original and not translated:
            return
        timestamp = str(data.get("timestamp") or data.get("backend_timestamp") or "")
        item = {"timestamp": timestamp, "original": original, "translated": translated}
        index = next((i for i, sub in enumerate(self.subtitles) if timestamp and sub["timestamp"] == timestamp), -1)
        if index >= 0:
            self.subtitles[index] = item
        else:
            self.subtitles.append(item)
        self.subtitles = self.subtitles[-max(1, self.settings.max_items):]

    def _open_settings(self) -> None:
        self._remember_geometry()
        if open_settings_dialog(self.settings):
            save_settings(self.settings)
            self._start_client()
            self.render()

    def render(self) -> None:
        if not self.hwnd:
            return
        width = max(420, self.settings.width)
        height = max(130, self.settings.height)
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        ctypes.memset(bits, 0, width * height * 4)

        graphics = ctypes.c_void_p()
        gdiplus.GdipCreateFromHDC(mem_dc, ctypes.byref(graphics))
        gdiplus.GdipSetSmoothingMode(graphics, 4)  # 4 = SmoothingModeAntiAlias
        gdiplus.GdipSetTextRenderingHint(graphics, 5)

        self._draw_background(graphics, width, height)
        self._draw_status(graphics, width)
        self._draw_subtitles(graphics, width, height)
        self._draw_toolbar(graphics, width)
        self._draw_size_grip(graphics, width, height)

        gdiplus.GdipDeleteGraphics(graphics)

        rect = RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        dst = POINT(rect.left, rect.top)
        size = SIZE(width, height)
        src = POINT(0, 0)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, screen_dc, ctypes.byref(dst), ctypes.byref(size), mem_dc, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)

        gdi32.SelectObject(mem_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def _draw_background(self, graphics: int, width: int, height: int) -> None:
        if self.mouse_over:
            alpha = int(max(0.0, min(1.0, self.settings.opacity)) * 180)
            if alpha < 45:
                alpha = 45
        else:
            alpha = int(max(0.0, min(1.0, self.settings.opacity)) * 125)
            
        self._fill_round_rect(graphics, 1, 1, width - 2, height - 2, 16, self.settings.background_color, alpha)
        
        if self.mouse_over:
            self._draw_round_rect_border(graphics, 1, 1, width - 2, height - 2, 16, "#38bdf8", 68, stroke_width=1.5)

    def _draw_round_rect_border(self, graphics: int, x: int, y: int, w: int, h: int, radius: int, color: str, alpha: int, stroke_width: float = 1.0) -> None:
        radius = max(1, min(radius, int(w / 2), int(h / 2)))
        diameter = radius * 2
        path = ctypes.c_void_p()
        pen = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        gdiplus.GdipAddPathArc(path, float(x), float(y), float(diameter), float(diameter), 180.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + radius), float(y), float(x + w - radius), float(y))
        gdiplus.GdipAddPathArc(path, float(x + w - diameter), float(y), float(diameter), float(diameter), 270.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + w), float(y + radius), float(x + w), float(y + h - radius))
        gdiplus.GdipAddPathArc(path, float(x + w - diameter), float(y + h - diameter), float(diameter), float(diameter), 0.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + w - radius), float(y + h), float(x + radius), float(y + h))
        gdiplus.GdipAddPathArc(path, float(x), float(y + h - diameter), float(diameter), float(diameter), 90.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x), float(y + h - radius), float(x), float(y + radius))
        gdiplus.GdipClosePathFigure(path)
        gdiplus.GdipCreatePen1(argb(alpha, color), stroke_width, 2, ctypes.byref(pen))
        gdiplus.GdipSetPenLineJoin(pen, 2)
        gdiplus.GdipDrawPath(graphics, pen, path)
        gdiplus.GdipDeletePen(pen)
        gdiplus.GdipDeletePath(path)

    def _draw_status(self, graphics: int, width: int) -> None:
        if not self.settings.show_status or self.compact or not getattr(self, "mouse_over", True):
            return
        
        if self.status_type == "connected":
            color = "#20d477"
            bg_color = "#0b2b1a"
            border_color = "#165935"
        elif self.status_type == "error":
            color = "#ff4b5f"
            bg_color = "#360f14"
            border_color = "#6e1a23"
        else:
            color = "#f59e0b"
            bg_color = "#332005"
            border_color = "#66410a"
            
        badge_w = 168
        badge_h = 22
        bx, by = 14, 12
        
        self._fill_round_rect(graphics, bx, by, badge_w, badge_h, 11, bg_color, 160)
        self._draw_round_rect_border(graphics, bx, by, badge_w, badge_h, 11, border_color, 180, stroke_width=1.0)
        self._draw_text(graphics, "●", bx + 8, by + 1, 16, 20, 9, color, bold=True)
        self._draw_text(graphics, self.status_text, bx + 22, by + 4, badge_w - 28, 16, 8, "#d7deea", bold=False)

    def _draw_toolbar(self, graphics: int, width: int) -> None:
        if self.compact or not getattr(self, "mouse_over", True):
            return
            
        rect = RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        cursor_pos = POINT()
        user32.GetCursorPos(ctypes.byref(cursor_pos))
        rx = cursor_pos.x - rect.left
        ry = cursor_pos.y - rect.top
        
        for name, left, top, right, bottom in self._button_rects():
            btn_hover = (left <= rx <= right and top <= ry <= bottom)
            
            if name == "close":
                fill = "#ef4444" if btn_hover else "#2d1418"
                alpha = 220 if btn_hover else 125
                txt_color = "#ffffff" if btn_hover else "#f87171"
            elif name == "settings":
                fill = "#0ea5e9" if btn_hover else "#151d2a"
                alpha = 220 if btn_hover else 125
                txt_color = "#ffffff" if btn_hover else "#38bdf8"
            else:
                fill = "#0d9488" if btn_hover else "#131f24"
                alpha = 220 if btn_hover else 125
                txt_color = "#ffffff" if btn_hover else "#2dd4bf"
                
            self._fill_round_rect(graphics, left, top, right - left, bottom - top, 8, fill, alpha)
            if btn_hover:
                self._draw_round_rect_border(graphics, left, top, right - left, bottom - top, 8, "#ffffff", 140, stroke_width=1.0)
                
            text = "⚙" if name == "settings" else "⇄" if name == "compact" else "×"
            self._draw_text(graphics, text, left, top + 1, right - left, bottom - top, 10, txt_color, bold=True, center=True, valign=True, alpha=255)

    def _draw_size_grip(self, graphics: int, width: int, height: int) -> None:
        if not getattr(self, "mouse_over", True):
            return
        self._fill_round_rect(graphics, width - 13, height - 13, 10, 10, 3, "#38bdf8", 120)

    def _draw_subtitles(self, graphics: int, width: int, height: int) -> None:
        if not self.subtitles:
            self._draw_text(graphics, "等待字幕...", 0, height / 2 - 18, width, 40, 16, "#858b96", bold=True, center=True, valign=True)
            return

        left = 14
        marker_x = 7
        text_x = 17
        bottom = float(height - 10)
        block_gap = 17
        
        # Room for status bar at the top if visible and not compact
        top_limit = 42 if (self.settings.show_status and not self.compact and getattr(self, "mouse_over", True)) else 12
        available_h = bottom - top_limit
        
        # Sizing loop
        base_size = self.settings.font_size
        size = max(12, base_size - 3)
        line_gap = 8
        max_wrap_w = 760
        
        max_content_w = 180
        block_defs = []
        
        for sub in self.subtitles[-max(1, self.settings.max_items):]:
            lines = []
            if self.settings.show_original and sub["original"]:
                lines.append((sub["original"], self.settings.original_color, size))
            if self.settings.show_translated and sub["translated"]:
                lines.append((sub["translated"], self.settings.translated_color, size))
            if not lines:
                continue
            
            line_sizes = [self._measure_text_size(graphics, text, max_wrap_w, line_size) for text, _, line_size in lines]
            heights = [item[1] for item in line_sizes]
            widths = [item[0] for item in line_sizes]
            
            block_w = max(widths) if widths else 180
            if block_w > max_content_w:
                max_content_w = block_w
                
            block_h = sum(heights) + line_gap * max(0, len(heights) - 1)
            block_defs.append((sub, lines, heights, block_h, line_gap))
            
        total_h = sum(item[3] for item in block_defs) + block_gap * max(0, len(block_defs) - 1)
        
        # Ideal adaptive size
        ideal_w = max(420, min(1000, max_content_w + 64))
        ideal_h = max(130, min(600, total_h + top_limit + 16))
        
        # If window size differs significantly from ideal size, trigger physical resize.
        # Use an 8px tolerance to avoid infinite jitter/resize loops due to High-DPI scaling or DWM border discrepancies.
        if abs(width - ideal_w) > 8 or abs(height - ideal_h) > 8:
            # SWP_NOMOVE = 0x0002, SWP_NOZORDER = 0x0004, SWP_NOACTIVATE = 0x0010
            user32.SetWindowPos(self.hwnd, None, 0, 0, ideal_w, ideal_h, 0x0016)

            
        # Draw subtitles centered vertically
        top_cursor = max(top_limit, int(top_limit + (available_h - total_h) / 2))
        text_w = max(180, width - 58)
        
        for idx, (_sub, lines, heights, block_h, line_gap) in enumerate(block_defs):
            if top_cursor + block_h > height - 4:
                break
            self._fill_round_rect(graphics, marker_x, top_cursor + 1, 3, max(12, block_h - 2), 2, self.settings.translated_color, 255)
            y = top_cursor - 2
            for line_index, ((text, color, line_size), line_h) in enumerate(zip(lines, heights)):
                self._draw_text(
                    graphics,
                    text,
                    text_x,
                    y,
                    text_w,
                    line_h + 6,
                    line_size,
                    color,
                    bold=True,
                    outline=True,
                    center=True,
                    alpha=255,
                )
                y += line_h + line_gap
                
            top_cursor += block_h + block_gap

    def _font(self, size: int, bold: bool) -> tuple[ctypes.c_void_p, ctypes.c_void_p]:
        family = ctypes.c_void_p()
        font = ctypes.c_void_p()
        gdiplus.GdipCreateFontFamilyFromName("Microsoft JhengHei UI", None, ctypes.byref(family))
        gdiplus.GdipCreateFont(family, ctypes.c_float(float(size)), 1 if bold else 0, 2, ctypes.byref(font))
        return family, font

    def _draw_text(
        self,
        graphics: int,
        text: str,
        x: float,
        y: float,
        w: float,
        h: float,
        size: int,
        color: str,
        bold: bool = False,
        center: bool = False,
        valign: bool = False,
        outline: bool = False,
        alpha: int = 255,
    ) -> None:
        family, font = self._font(size, bold)
        fmt = self._string_format(center, valign)
        x = round(float(x))
        y = round(float(y))
        w = round(float(w))
        h = round(float(h))
        if outline:
            self._draw_text_path(graphics, text, family, fmt, x, y, w, h, size, color, bold, alpha)
        else:
            self._draw_text_rect(graphics, text, font, fmt, x, y, w, h, color, alpha)
        gdiplus.GdipDeleteStringFormat(fmt)
        gdiplus.GdipDeleteFont(font)
        gdiplus.GdipDeleteFontFamily(family)

    def _draw_text_path(
        self,
        graphics: int,
        text: str,
        family: ctypes.c_void_p,
        fmt: ctypes.c_void_p,
        x: float,
        y: float,
        w: float,
        h: float,
        size: int,
        color: str,
        bold: bool,
        alpha: int,
        stroke_color: str = "#000000",
        stroke_width: float = 5.0,
        shadow: bool = True,
    ) -> None:
        path = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        
        style = 1 if bold else 0
        rect = RectF(float(x), float(y), float(w), float(h))
        em_size = float(size)
        
        if shadow:
            shadow_path = ctypes.c_void_p()
            gdiplus.GdipCreatePath(0, ctypes.byref(shadow_path))
            offset = max(1.5, size * 0.055)
            shadow_rect = RectF(float(x + offset), float(y + offset), float(w), float(h))
            gdiplus.GdipAddPathString(shadow_path, text, -1, family, style, em_size, ctypes.byref(shadow_rect), fmt)
            
            shadow_pen = ctypes.c_void_p()
            gdiplus.GdipCreatePen1(argb(110, "#000000"), stroke_width + 1.0, 2, ctypes.byref(shadow_pen))
            gdiplus.GdipSetPenLineJoin(shadow_pen, 2)
            gdiplus.GdipDrawPath(graphics, shadow_pen, shadow_path)
            
            shadow_brush = ctypes.c_void_p()
            gdiplus.GdipCreateSolidFill(argb(130, "#000000"), ctypes.byref(shadow_brush))
            gdiplus.GdipFillPath(graphics, shadow_brush, shadow_path)
            
            gdiplus.GdipDeleteBrush(shadow_brush)
            gdiplus.GdipDeletePen(shadow_pen)
            gdiplus.GdipDeletePath(shadow_path)

        gdiplus.GdipAddPathString(path, text, -1, family, style, em_size, ctypes.byref(rect), fmt)
        
        pen = ctypes.c_void_p()
        gdiplus.GdipCreatePen1(argb(230, stroke_color), stroke_width, 2, ctypes.byref(pen))
        gdiplus.GdipSetPenLineJoin(pen, 2)
        gdiplus.GdipDrawPath(graphics, pen, path)
        
        brush = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(argb(alpha, color), ctypes.byref(brush))
        gdiplus.GdipFillPath(graphics, brush, path)
        
        gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeletePen(pen)
        gdiplus.GdipDeletePath(path)

    def _draw_text_rect(
        self,
        graphics: int,
        text: str,
        font: ctypes.c_void_p,
        fmt: ctypes.c_void_p,
        x: float,
        y: float,
        w: float,
        h: float,
        color: str,
        alpha: int,
    ) -> None:
        brush = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(argb(alpha, color), ctypes.byref(brush))
        rect = RectF(float(x), float(y), float(w), float(h))
        gdiplus.GdipDrawString(graphics, text, -1, font, ctypes.byref(rect), fmt, brush)
        gdiplus.GdipDeleteBrush(brush)

    def _fill_rect(self, graphics: int, x: int, y: int, w: int, h: int, color: str, alpha: int) -> None:
        brush = ctypes.c_void_p()
        gdiplus.GdipCreateSolidFill(argb(alpha, color), ctypes.byref(brush))
        gdiplus.GdipFillRectangleI(graphics, brush, int(x), int(y), int(w), int(h))
        gdiplus.GdipDeleteBrush(brush)

    def _fill_round_rect(self, graphics: int, x: int, y: int, w: int, h: int, radius: int, color: str, alpha: int) -> None:
        radius = max(1, min(radius, int(w / 2), int(h / 2)))
        diameter = radius * 2
        path = ctypes.c_void_p()
        brush = ctypes.c_void_p()
        gdiplus.GdipCreatePath(0, ctypes.byref(path))
        gdiplus.GdipAddPathArc(path, float(x), float(y), float(diameter), float(diameter), 180.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + radius), float(y), float(x + w - radius), float(y))
        gdiplus.GdipAddPathArc(path, float(x + w - diameter), float(y), float(diameter), float(diameter), 270.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + w), float(y + radius), float(x + w), float(y + h - radius))
        gdiplus.GdipAddPathArc(path, float(x + w - diameter), float(y + h - diameter), float(diameter), float(diameter), 0.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x + w - radius), float(y + h), float(x + radius), float(y + h))
        gdiplus.GdipAddPathArc(path, float(x), float(y + h - diameter), float(diameter), float(diameter), 90.0, 90.0)
        gdiplus.GdipAddPathLine(path, float(x), float(y + h - radius), float(x), float(y + radius))
        gdiplus.GdipClosePathFigure(path)
        gdiplus.GdipCreateSolidFill(argb(alpha, color), ctypes.byref(brush))
        gdiplus.GdipFillPath(graphics, brush, path)
        gdiplus.GdipDeleteBrush(brush)
        gdiplus.GdipDeletePath(path)

    def _string_format(self, center: bool = False, valign: bool = False) -> ctypes.c_void_p:
        fmt = ctypes.c_void_p()
        status = gdiplus.GdipStringFormatGetGenericTypographic(ctypes.byref(fmt))
        if status != 0 or not fmt:
            gdiplus.GdipCreateStringFormat(0, 0, ctypes.byref(fmt))
        gdiplus.GdipSetStringFormatFlags(fmt, 0x00000800)
        if center:
            gdiplus.GdipSetStringFormatAlign(fmt, 1)
        if valign:
            gdiplus.GdipSetStringFormatLineAlign(fmt, 1)
        return fmt

    def _measure_text_size(self, graphics: int, text: str, width: int, size: int) -> tuple[int, int]:
        family, font = self._font(size, True)
        fmt = self._string_format()
        layout = RectF(0, 0, float(width), 5000.0)
        bounds = RectF()
        gdiplus.GdipMeasureString(graphics, text, -1, font, ctypes.byref(layout), fmt, ctypes.byref(bounds), None, None)
        gdiplus.GdipDeleteStringFormat(fmt)
        gdiplus.GdipDeleteFont(font)
        gdiplus.GdipDeleteFontFamily(family)
        return int(bounds.Width + 8), max(size + 8, int(bounds.Height + 6))


def open_settings_dialog(settings: Settings) -> bool:
    from tkinter import colorchooser
    
    def is_light(hex_color: str) -> bool:
        try:
            r, g, b = hex_to_rgb(hex_color)
            return ((r * 299) + (g * 587) + (b * 114)) / 1000 > 125
        except Exception:
            return False

    saved = {"value": False}
    root = tk.Tk()
    root.title("字幕視窗設定")
    root.configure(bg="#0f172a")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    server_var = tk.StringVar(value=settings.server)
    font_var = tk.IntVar(value=settings.font_size)
    max_var = tk.IntVar(value=settings.max_items)
    opacity_var = tk.DoubleVar(value=settings.opacity)
    original_var = tk.BooleanVar(value=settings.show_original)
    translated_var = tk.BooleanVar(value=settings.show_translated)
    status_var = tk.BooleanVar(value=settings.show_status)
    top_var = tk.BooleanVar(value=settings.always_on_top)

    body = tk.Frame(root, bg="#0f172a", padx=20, pady=20)
    body.pack(fill="both", expand=True)

    f_title = ("Microsoft JhengHei UI", 9, "bold")
    f_body = ("Microsoft JhengHei UI", 9)

    # 1. Connection Section Card
    card_conn = tk.LabelFrame(body, text=" 連線設定 ", bg="#0f172a", fg="#38bdf8", font=f_title, padx=12, pady=10, relief="solid", bd=1)
    card_conn.pack(fill="x", pady=(0, 10))

    tk.Label(card_conn, text="字幕分享網址或 IP:port", bg="#0f172a", fg="#94a3b8", font=f_body, anchor="w").pack(fill="x", pady=(0, 4))
    entry_server = tk.Entry(card_conn, textvariable=server_var, bg="#1e293b", fg="#ffffff", insertbackground="#ffffff", relief="flat", bd=4, font=f_body)
    entry_server.pack(fill="x")

    # 2. Subtitle Appearance Section Card
    card_style = tk.LabelFrame(body, text=" 字幕與色彩樣式 ", bg="#0f172a", fg="#38bdf8", font=f_title, padx=12, pady=10, relief="solid", bd=1)
    card_style.pack(fill="x", pady=10)

    tk.Label(card_style, text="字體大小", bg="#0f172a", fg="#94a3b8", font=f_body, anchor="w").pack(fill="x", pady=(0, 2))
    scale_font = tk.Scale(card_style, from_=14, to=72, orient="horizontal", variable=font_var, bg="#0f172a", fg="#ffffff", highlightthickness=0, bd=0, activebackground="#38bdf8")
    scale_font.pack(fill="x", pady=(0, 8))

    tk.Label(card_style, text="最多顯示筆數", bg="#0f172a", fg="#94a3b8", font=f_body, anchor="w").pack(fill="x", pady=(0, 2))
    scale_max = tk.Scale(card_style, from_=1, to=8, orient="horizontal", variable=max_var, bg="#0f172a", fg="#ffffff", highlightthickness=0, bd=0, activebackground="#38bdf8")
    scale_max.pack(fill="x", pady=(0, 8))

    tk.Label(card_style, text="背景透明度", bg="#0f172a", fg="#94a3b8", font=f_body, anchor="w").pack(fill="x", pady=(0, 2))
    scale_op = tk.Scale(card_style, from_=0.0, to=1.0, resolution=0.01, orient="horizontal", variable=opacity_var, bg="#0f172a", fg="#ffffff", highlightthickness=0, bd=0, activebackground="#38bdf8")
    scale_op.pack(fill="x", pady=(0, 12))

    color_lbl = tk.Label(card_style, text="色彩自訂（點擊色彩區塊開啟調色盤）", bg="#0f172a", fg="#94a3b8", font=f_title, anchor="w")
    color_lbl.pack(fill="x", pady=(0, 6))

    color_btn_frame = tk.Frame(card_style, bg="#0f172a")
    color_btn_frame.pack(fill="x")

    color_state = {
        "original_color": settings.original_color,
        "translated_color": settings.translated_color,
        "background_color": settings.background_color
    }

    def pick_color(key: str, btn: tk.Button) -> None:
        _, hex_val = colorchooser.askcolor(initialcolor=color_state[key], title="選擇字幕顏色", parent=root)
        if hex_val:
            color_state[key] = hex_val
            btn.configure(bg=hex_val, fg="#000000" if is_light(hex_val) else "#ffffff", activebackground=hex_val)

    btn_orig = tk.Button(color_btn_frame, text="原文顏色", bg=color_state["original_color"], fg="#000000" if is_light(color_state["original_color"]) else "#ffffff", relief="flat", bd=0, padx=10, pady=6, font=f_title, cursor="hand2")
    btn_orig.configure(command=lambda: pick_color("original_color", btn_orig), activebackground=color_state["original_color"])
    btn_orig.pack(side="left", expand=True, fill="x", padx=(0, 4))

    btn_trans = tk.Button(color_btn_frame, text="翻譯顏色", bg=color_state["translated_color"], fg="#000000" if is_light(color_state["translated_color"]) else "#ffffff", relief="flat", bd=0, padx=10, pady=6, font=f_title, cursor="hand2")
    btn_trans.configure(command=lambda: pick_color("translated_color", btn_trans), activebackground=color_state["translated_color"])
    btn_trans.pack(side="left", expand=True, fill="x", padx=2)

    btn_bg = tk.Button(color_btn_frame, text="背景顏色", bg=color_state["background_color"], fg="#000000" if is_light(color_state["background_color"]) else "#ffffff", relief="flat", bd=0, padx=10, pady=6, font=f_title, cursor="hand2")
    btn_bg.configure(command=lambda: pick_color("background_color", btn_bg), activebackground=color_state["background_color"])
    btn_bg.pack(side="left", expand=True, fill="x", padx=(4, 0))

    # 3. Display Options Card
    card_opt = tk.LabelFrame(body, text=" 視窗與功能選項 ", bg="#0f172a", fg="#38bdf8", font=f_title, padx=12, pady=10, relief="solid", bd=1)
    card_opt.pack(fill="x", pady=10)

    checkbox_frame = tk.Frame(card_opt, bg="#0f172a")
    checkbox_frame.pack(fill="x")

    options_list = [
        ("顯示原文", original_var),
        ("顯示翻譯", translated_var),
        ("顯示狀態列", status_var),
        ("永遠置頂", top_var),
    ]

    for idx, (txt, var) in enumerate(options_list):
        row = idx // 2
        col = idx % 2
        cb = tk.Checkbutton(checkbox_frame, text=txt, variable=var, bg="#0f172a", fg="#ffffff", selectcolor="#1e293b", activebackground="#0f172a", activeforeground="#ffffff", font=f_body, cursor="hand2")
        cb.grid(row=row, column=col, sticky="w", padx=16, pady=4)

    checkbox_frame.grid_columnconfigure(0, weight=1)
    checkbox_frame.grid_columnconfigure(1, weight=1)

    # 4. Action Buttons
    def save() -> None:
        server = normalize_server(server_var.get())
        if not server:
            messagebox.showerror("設定錯誤", "請輸入字幕分享網址，例如 http://192.168.1.10:8765", parent=root)
            return
        settings.server = server
        settings.font_size = int(font_var.get())
        settings.max_items = int(max_var.get())
        settings.opacity = float(opacity_var.get())
        settings.show_original = bool(original_var.get())
        settings.show_translated = bool(translated_var.get())
        settings.show_status = bool(status_var.get())
        settings.always_on_top = bool(top_var.get())
        settings.original_color = color_state["original_color"]
        settings.translated_color = color_state["translated_color"]
        settings.background_color = color_state["background_color"]
        
        saved["value"] = True
        root.destroy()

    btn_frame = tk.Frame(body, bg="#0f172a")
    btn_frame.pack(fill="x", pady=(16, 0))

    btn_save = tk.Button(btn_frame, text="儲存並重新連線", command=save, bg="#0ea5e9", activebackground="#38bdf8", fg="#ffffff", activeforeground="#ffffff", relief="flat", bd=0, padx=16, pady=8, font=f_title, cursor="hand2")
    btn_save.pack(side="left", expand=True, fill="x", padx=(0, 8))

    btn_cancel = tk.Button(btn_frame, text="取消", command=root.destroy, bg="#334155", activebackground="#475569", fg="#ffffff", activeforeground="#ffffff", relief="flat", bd=0, padx=16, pady=8, font=f_body, cursor="hand2")
    btn_cancel.pack(side="right", expand=True, fill="x", padx=(8, 0))

    root.update_idletasks()
    root.geometry(f"+{settings.x + 40}+{settings.y + 40}")
    root.mainloop()
    return saved["value"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--server", help="Subtitle API base URL, for example http://192.168.1.10:8765")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_settings()
    if args.server:
        settings.server = normalize_server(args.server)
        save_settings(settings)
    LayeredSubtitleWindow(settings).run()


if __name__ == "__main__":
    main()
