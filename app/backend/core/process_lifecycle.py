"""Windows process lifetime helpers for backend-owned child processes."""
import ctypes
import logging
import os
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobHandle = ctypes.c_void_p
_job_handle = None
_job_lock = threading.Lock()
_kernel = None


def _get_kernel():
    global _kernel
    if _kernel is None:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        kernel.CreateJobObjectW.restype = _JobHandle
        kernel.SetInformationJobObject.argtypes = [_JobHandle, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
        kernel.SetInformationJobObject.restype = ctypes.c_int
        kernel.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_uint]
        kernel.OpenProcess.restype = _JobHandle
        kernel.AssignProcessToJobObject.argtypes = [_JobHandle, _JobHandle]
        kernel.AssignProcessToJobObject.restype = ctypes.c_int
        kernel.TerminateJobObject.argtypes = [_JobHandle, ctypes.c_uint]
        kernel.TerminateJobObject.restype = ctypes.c_int
        kernel.CloseHandle.argtypes = [_JobHandle]
        kernel.CloseHandle.restype = ctypes.c_int
        _kernel = kernel
    return _kernel


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint),
        ("SchedulingClass", ctypes.c_uint),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _get_job_handle():
    global _job_handle
    if sys.platform != "win32":
        return None
    with _job_lock:
        if _job_handle:
            return _job_handle
        try:
            kernel = _get_kernel()
            handle = kernel.CreateJobObjectW(None, None)
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            info = _ExtendedLimitInformation()
            info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
                error = ctypes.WinError(ctypes.get_last_error())
                kernel.CloseHandle(handle)
                raise error
            _job_handle = handle
        except Exception:
            logger.warning("Could not create backend child-process job; children may outlive backend", exc_info=True)
            return None
        return _job_handle


def assign_process(process):
    """Assign a newly spawned backend-owned process to the lifetime job."""
    handle = _get_job_handle()
    if handle is None or process is None:
        return False
    try:
        kernel = _get_kernel()
        process_handle = getattr(process, "_handle", None)
        opened_handle = not process_handle
        if opened_handle:
            process_handle = kernel.OpenProcess(0x0001 | 0x0100, False, int(process.pid))
            if not process_handle:
                raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())
        if opened_handle:
            kernel.CloseHandle(process_handle)
        return True
    except Exception:
        logger.warning("Could not assign child PID %s to backend job", getattr(process, "pid", "?"), exc_info=True)
        return False


class TranslationJob:
    """Own one engine job; serialize completion and Stop handle cleanup."""

    def __init__(self, handle):
        self.handle = handle
        self._lock = threading.Lock()

    def close(self, terminate=False):
        with self._lock:
            if self.handle is None:
                return
            kernel = _get_kernel()
            handle, self.handle = self.handle, None
            try:
                if terminate and not kernel.TerminateJobObject(handle, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel.CloseHandle(handle)


def create_translation_job(process):
    """Assign immediately after spawn; taskkill remains the failure fallback."""
    if sys.platform != "win32":
        return None
    handle = None
    try:
        kernel = _get_kernel()
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimitInformation()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel.AssignProcessToJobObject(handle, process._handle):
            raise ctypes.WinError(ctypes.get_last_error())
        return TranslationJob(handle)
    except Exception:
        if handle:
            kernel.CloseHandle(handle)
        logger.warning("Could not create/assign translation job; using taskkill fallback", exc_info=True)
        return None


def kill_process_tree(process, timeout=5, job=None):
    """Terminate a process and descendants on Windows; retain standard behavior elsewhere."""
    if os.name == "nt" and job is not None:
        try:
            job.close(terminate=True)
        except Exception:
            logger.warning("Could not terminate translation job", exc_info=True)
        else:
            if process is not None:
                try:
                    process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("Process did not exit after job termination")
            return
    if process is None:
        return
    if os.name != "nt" and process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.warning("taskkill failed for process tree PID %s", process.pid, exc_info=True)
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("Process PID %s did not exit after tree termination", process.pid)
