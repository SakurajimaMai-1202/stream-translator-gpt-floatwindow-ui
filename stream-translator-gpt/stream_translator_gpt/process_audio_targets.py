"""Lightweight Windows target discovery; safe to import in the frozen GUI."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import PureWindowsPath
import sys

MIN_WINDOWS_BUILD = 20348


def platform_support() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "指定應用程式音訊僅支援 Windows。"
    if sys.getwindowsversion().build < MIN_WINDOWS_BUILD:
        return False, "指定應用程式音訊需要 Windows build 20348 或更新版本。"
    return True, "擷取指定程序及其子程序；同一瀏覽器的其他分頁可能一起被擷取。"


def _apis():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.IsWindow.argtypes = [wintypes.HWND]
    user.IsWindow.restype = wintypes.BOOL
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsWindowVisible.restype = wintypes.BOOL
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextLengthW.restype = ctypes.c_int
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.restype = ctypes.c_int
    return kernel, user


def _identity(pid: int, kernel) -> dict:
    handle = kernel.OpenProcess(0x1000 | 0x00100000, False, pid)  # query + synchronize
    if not handle:
        raise ValueError("無法存取目標程序，請重新選擇可存取的應用程式。")
    try:
        if kernel.WaitForSingleObject(handle, 0) != 0x102:
            raise ValueError("目標程序已退出，請重新選擇。")
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ValueError("無法驗證目標程序建立時間。")
        size = wintypes.DWORD(32768)
        path = ctypes.create_unicode_buffer(size.value)
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise ValueError("無法識別目標程式。")
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return {"process_id": pid, "process_start_time": str(created),
                "process_name": PureWindowsPath(path.value).name, "path": path.value}
    finally:
        kernel.CloseHandle(handle)


def _parents(kernel) -> dict[int, int]:
    class Entry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        fn = getattr(kernel, name)
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
        fn.restype = wintypes.BOOL
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, ctypes.c_void_p(-1).value):
        return {}
    try:
        entry = Entry()
        entry.dwSize = ctypes.sizeof(entry)
        result = {}
        found = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            result[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            found = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        return result
    finally:
        kernel.CloseHandle(snapshot)


def _capture_root(identity: dict, parents: dict[int, int], kernel) -> dict:
    """Follow only older parents with the exact same image path, never launchers."""
    # Browser windows may belong to a renderer while audio belongs to a sibling.
    # Generic same-image parents (e.g. Python hosts) may run unrelated applications.
    if identity['process_name'].casefold() not in {'chrome.exe', 'msedge.exe', 'brave.exe', 'opera.exe', 'firefox.exe', 'vivaldi.exe'}:
        return identity
    visited = {identity["process_id"]}
    while (parent := parents.get(identity["process_id"])) and parent not in visited:
        visited.add(parent)
        try:
            candidate = _identity(parent, kernel)
        except ValueError:
            break
        if (candidate["path"].casefold() != identity["path"].casefold()
                or int(candidate["process_start_time"]) >= int(identity["process_start_time"])):
            break
        identity = candidate
    return identity


def list_process_audio_targets() -> dict:
    supported, message = platform_support()
    if not supported:
        return {"supported": False, "message": message, "targets": []}
    kernel, user = _apis()
    parents = _parents(kernel)
    targets = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        length = user.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user.GetWindowTextW(hwnd, title, length + 1)
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            identity = _capture_root(_identity(pid.value, kernel), parents, kernel)
        except ValueError:
            return True
        targets.append({k: v for k, v in identity.items() if k != "path"} | {
            "window_handle": str(int(hwnd)), "window_process_id": int(pid.value), "title": title.value})
        return True

    callback = callback_type(visit)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows.restype = wintypes.BOOL
    if not user.EnumWindows(callback, 0):
        raise RuntimeError("無法列出目前視窗。")
    targets.sort(key=lambda item: (item["process_name"].casefold(), item["title"].casefold()))
    return {"supported": True, "message": message, "targets": targets}


def validate_process_target(process_id: int, process_start_time: str, window_handle: str | None = None) -> dict:
    supported, message = platform_support()
    if not supported:
        raise ValueError(message)
    try:
        pid, created = int(process_id), int(process_start_time)
        if not 0 < pid <= 0xFFFFFFFF or not 0 < created <= 0xFFFFFFFFFFFFFFFF:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise ValueError("請重新選擇有效的應用程式目標。") from None
    kernel, user = _apis()
    identity = _identity(pid, kernel)
    if int(identity["process_start_time"]) != created:
        raise ValueError("目標程序已更換，請重新選擇。")
    if window_handle is not None:
        try:
            hwnd = int(window_handle)
            if not 0 < hwnd <= (1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise ValueError("視窗識別無效，請重新選擇。") from None
        if not user.IsWindow(hwnd):
            raise ValueError("目標視窗已關閉，請重新選擇。")
        window_pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        root = _capture_root(_identity(window_pid.value, kernel), _parents(kernel), kernel)
        if (root["process_id"], root["process_start_time"]) != (pid, str(created)):
            raise ValueError("目標視窗已更換，請重新選擇。")
    return {k: v for k, v in identity.items() if k != "path"}
