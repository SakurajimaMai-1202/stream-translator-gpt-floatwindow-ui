"""Launch native tools without inheriting the frozen GUI's DLL overrides."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading

_launch_lock = threading.RLock()


def popen_external(args, **kwargs):
    executable = Path(args[0]).resolve()
    args = [str(executable), *args[1:]]
    kwargs.setdefault("cwd", str(executable.parent))
    env = dict(kwargs.pop("env", os.environ))
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        root = os.path.normcase(os.path.abspath(bundle))
        def bundled(entry):
            path = os.path.normcase(os.path.abspath(entry.strip('"')))
            return path == root or path.startswith(root + os.sep)
        env["PATH"] = os.pathsep.join(
            entry for entry in env.get("PATH", "").split(os.pathsep)
            if entry and not bundled(entry)
        )
    kwargs["env"] = env
    with _launch_lock:
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            return subprocess.Popen(args, **kwargs)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetDllDirectoryW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p]
        kernel.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
        size = kernel.GetDllDirectoryW(0, None)
        previous = ctypes.create_unicode_buffer(size + 1)
        kernel.GetDllDirectoryW(len(previous), previous)
        if not kernel.SetDllDirectoryW(None):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            return subprocess.Popen(args, **kwargs)
        finally:
            kernel.SetDllDirectoryW(previous.value or None)


def run_external(args, *, capture_output=False, timeout=None, check=False, **kwargs):
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with popen_external(args, **kwargs) as process:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except BaseException:
            process.kill()
            process.communicate()
            raise
        result = subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
