import ctypes
import inspect
import os
import subprocess
import sys

import pytest
from backend.core import external_process as external
from backend.core.translator import TranslationContext


def test_translation_runtime_uses_isolated_external_launcher():
    source = inspect.getsource(TranslationContext._process_loop)
    assert "popen_external(" in source
    assert "subprocess.Popen(" not in source


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
    ffmpeg = tmp_path / "ffmpeg" / "bin"
    ffmpeg.mkdir(parents=True)
    working_directory = tmp_path / "working"
    working_directory.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    inherited_path = os.pathsep.join((str(ffmpeg), str(bundle), str(tmp_path / "driver")))
    monkeypatch.setenv("PATH", inherited_path)
    sentinel = object()
    def spawn(args, **kwargs):
        assert current() == ""
        assert kwargs["env"]["PATH"] == os.pathsep.join((str(ffmpeg), str(tmp_path / "driver")))
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["cwd"] == str(working_directory)
        if fail:
            raise OSError("spawn failed")
        return sentinel
    monkeypatch.setattr(subprocess, "Popen", spawn)
    try:
        kernel.SetDllDirectoryW(str(bundle))
        launch_kwargs = {
            "cwd": str(working_directory),
            "env": {"PATH": inherited_path, "PYTHONUTF8": "1"},
        }
        if fail:
            with pytest.raises(OSError, match="spawn failed"):
                external.popen_external([str(tmp_path / "tool.exe")], **launch_kwargs)
        else:
            assert external.popen_external([str(tmp_path / "tool.exe")], **launch_kwargs) is sentinel
        assert current() == str(bundle)
    finally:
        kernel.SetDllDirectoryW(original or None)
