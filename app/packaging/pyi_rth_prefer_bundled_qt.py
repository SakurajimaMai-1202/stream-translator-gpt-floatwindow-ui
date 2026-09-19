"""Prefer the bundled Qt DLLs before PyInstaller imports any PyQt6 modules."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


_dll_directory_handles = []

if sys.platform == "win32" and getattr(sys, "frozen", False):
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    qt_bin = bundle_root / "PyQt6" / "Qt6" / "bin"
    if qt_bin.is_dir():
        qt_bin_text = str(qt_bin)
        os.environ["PATH"] = qt_bin_text + os.pathsep + os.environ.get("PATH", "")
        ctypes.windll.kernel32.SetDllDirectoryW(qt_bin_text)
        if hasattr(os, "add_dll_directory"):
            _dll_directory_handles.append(os.add_dll_directory(qt_bin_text))
