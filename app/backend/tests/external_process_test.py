import ctypes
import os
import subprocess
import sys

import pytest
from backend.core import external_process as external


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DLL inheritance")
@pytest.mark.parametrize("fail", [False, True])
def test_frozen_launch_clears_dll_override_and_restores_it(monkeypatch, tmp_path, fail):
    kernel = ctypes.WinDLL("kernel32")
    kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
    def current():
        buffer = ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(buffer), buffer)
        return buffer.value
    original = current()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("PATH", str(bundle) + os.pathsep + str(tmp_path / "driver"))
    sentinel = object()
    def spawn(args, **kwargs):
        assert current() == ""
        assert kwargs["env"]["PATH"] == str(tmp_path / "driver")
        assert kwargs["cwd"] == str(tmp_path)
        if fail:
            raise OSError("spawn failed")
        return sentinel
    monkeypatch.setattr(subprocess, "Popen", spawn)
    try:
        kernel.SetDllDirectoryW(str(bundle))
        if fail:
            with pytest.raises(OSError, match="spawn failed"):
                external.popen_external([str(tmp_path / "tool.exe")])
        else:
            assert external.popen_external([str(tmp_path / "tool.exe")]) is sentinel
        assert current() == str(bundle)
    finally:
        kernel.SetDllDirectoryW(original or None)
