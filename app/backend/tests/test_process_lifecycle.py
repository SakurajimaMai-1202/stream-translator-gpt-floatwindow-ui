import ctypes
import os
import subprocess
import sys
import time

import pytest

from backend.core import process_lifecycle as lifecycle
from backend.core import translator


def test_assign_process_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(lifecycle.sys, "platform", "linux")
    assert lifecycle.assign_process(type("Process", (), {"pid": 123})()) is False


def test_assignment_failure_is_logged_and_continues(monkeypatch, caplog):
    monkeypatch.setattr(lifecycle.sys, "platform", "win32")
    monkeypatch.setattr(lifecycle, "_get_job_handle", lambda: object())
    monkeypatch.setattr(lifecycle.ctypes, "WinDLL", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied")), raising=False)
    assert lifecycle.assign_process(type("Process", (), {"pid": 123})()) is False
    assert "Could not assign child PID 123" in caplog.text


def test_assign_process_prefers_popen_handle(monkeypatch):
    calls = []
    process_handle = object()
    kernel = type("Kernel", (), {
        "AssignProcessToJobObject": staticmethod(lambda job, child: calls.append((job, child)) or 1),
        "OpenProcess": staticmethod(lambda *args: pytest.fail("Popen handle should be preferred")),
    })()
    monkeypatch.setattr(lifecycle, "_get_job_handle", lambda: "job")
    monkeypatch.setattr(lifecycle, "_get_kernel", lambda: kernel)
    process = type("Process", (), {"pid": 123, "_handle": process_handle})()
    assert lifecycle.assign_process(process)
    assert calls == [("job", process_handle)]


def test_assign_process_fallback_requests_terminate_and_set_quota(monkeypatch):
    calls = []
    kernel = type("Kernel", (), {
        "OpenProcess": staticmethod(lambda access, inherit, pid: calls.append((access, inherit, pid)) or "child"),
        "AssignProcessToJobObject": staticmethod(lambda job, child: 1),
        "CloseHandle": staticmethod(lambda child: calls.append(("close", child))),
    })()
    monkeypatch.setattr(lifecycle, "_get_job_handle", lambda: "job")
    monkeypatch.setattr(lifecycle, "_get_kernel", lambda: kernel)
    process = type("Process", (), {"pid": 123})()
    assert lifecycle.assign_process(process)
    assert calls == [(0x0001 | 0x0100, False, 123), ("close", "child")]


def test_windows_job_close_kills_assigned_child():
    if sys.platform != "win32":
        pytest.skip("Windows Job Objects are only available on Windows")
    job = lifecycle._get_job_handle()
    assert job
    process = subprocess.Popen(
        ["cmd", "/c", "ping", "-n", "30", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        assert lifecycle.assign_process(process)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [lifecycle._JobHandle]
        assert kernel.CloseHandle(job)
        lifecycle._job_handle = None
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if lifecycle._job_handle:
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CloseHandle(lifecycle._job_handle)
            lifecycle._job_handle = None


def test_kill_process_tree_uses_taskkill_on_windows(monkeypatch):
    calls = []

    class Process:
        pid = 987
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            calls.append("kill")
            self.returncode = -9

        def wait(self, timeout):
            calls.append("wait")

    process = Process()
    monkeypatch.setattr(lifecycle.os, "name", "nt")
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda command, **kwargs: calls.append(command))
    lifecycle.kill_process_tree(process)
    assert calls[0] == ["taskkill", "/F", "/T", "/PID", "987"]
    assert "kill" in calls


def test_translation_stop_uses_tree_kill_on_windows(monkeypatch):
    calls = []

    class Process:
        pid = 777

        def poll(self):
            return None

    monkeypatch.setattr(translator.os, "name", "nt")
    monkeypatch.setattr(translator, "kill_process_tree", lambda process, job=None: calls.append(process))
    context = translator.TranslationContext({}, "task")
    context.process = Process()
    import asyncio
    asyncio.run(context.stop())
    assert calls == [context.process]


@pytest.mark.parametrize("exited", [False, True])
def test_translation_stop_passes_job_even_after_root_exit(monkeypatch, exited):
    import asyncio
    calls = []
    context = translator.TranslationContext({}, "job-stop")
    context.process = type("Process", (), {"pid": 777, "poll": lambda self: 0 if exited else None})()
    context.process_job = object()
    monkeypatch.setattr(translator.os, "name", "nt")
    monkeypatch.setattr(translator, "persistent_process", None)
    monkeypatch.setattr(translator, "kill_process_tree", lambda process, job: calls.append((process, job)))
    asyncio.run(context.stop())
    assert calls == [(context.process, context.process_job)]


def test_job_stop_terminates_then_closes_once_after_root_exit(monkeypatch):
    calls = []
    kernel = type("Kernel", (), {
        "TerminateJobObject": staticmethod(lambda handle, code: calls.append(("terminate", handle)) or 1),
        "CloseHandle": staticmethod(lambda handle: calls.append(("close", handle)) or 1),
    })()
    monkeypatch.setattr(lifecycle, "_get_kernel", lambda: kernel)
    monkeypatch.setattr(lifecycle.os, "name", "nt")
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda *a, **kw: pytest.fail("job owns descendants"))
    process = type("Process", (), {"poll": lambda self: 0, "wait": lambda self, timeout: 0})()
    job = lifecycle.TranslationJob("job")
    lifecycle.kill_process_tree(process, job=job)
    job.close()
    lifecycle.kill_process_tree(process, job=job)
    assert calls == [("terminate", "job"), ("close", "job")]


def test_normal_completion_closes_job_once(monkeypatch):
    calls = []
    kernel = type("Kernel", (), {"CloseHandle": staticmethod(lambda handle: calls.append(handle))})()
    monkeypatch.setattr(lifecycle, "_get_kernel", lambda: kernel)
    job = lifecycle.TranslationJob("job")
    job.close()
    job.close()
    assert calls == ["job"]


@pytest.mark.parametrize("failure", ["create", "configure", "assign", None])
def test_translation_job_setup_and_failure_cleanup(monkeypatch, failure):
    calls = []
    def create(*args):
        if failure == "create":
            raise OSError("denied")
        return "job"
    def configure(handle, kind, info, size):
        limits = ctypes.cast(info, ctypes.POINTER(lifecycle._ExtendedLimitInformation)).contents
        assert limits.BasicLimitInformation.LimitFlags == lifecycle._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if failure == "configure":
            raise OSError("denied")
        return 1
    def assign(handle, process):
        assert process == "process"
        if failure == "assign":
            raise OSError("denied")
        return 1
    kernel = type("Kernel", (), {
        "CreateJobObjectW": staticmethod(create),
        "SetInformationJobObject": staticmethod(configure),
        "AssignProcessToJobObject": staticmethod(assign),
        "CloseHandle": staticmethod(lambda handle: calls.append(handle)),
    })()
    monkeypatch.setattr(lifecycle.sys, "platform", "win32")
    monkeypatch.setattr(lifecycle, "_get_kernel", lambda: kernel)
    job = lifecycle.create_translation_job(type("Process", (), {"_handle": "process"})())
    assert (job is None) == (failure is not None)
    assert calls == (["job"] if failure in {"configure", "assign"} else [])
    if job:
        job.close()


def test_taskkill_fallback_runs_even_after_root_exit(monkeypatch):
    calls = []
    monkeypatch.setattr(lifecycle.os, "name", "nt")
    monkeypatch.setattr(lifecycle.subprocess, "CREATE_NO_WINDOW", 0, raising=False)
    monkeypatch.setattr(lifecycle.subprocess, "run", lambda command, **kw: calls.append(command))
    process = type("Process", (), {"pid": 123, "poll": lambda self: 0, "wait": lambda self, timeout: 0})()
    lifecycle.kill_process_tree(process)
    assert calls == [["taskkill", "/F", "/T", "/PID", "123"]]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Objects required")
def test_stop_kills_descendant_after_root_exits():
    import asyncio

    class ProcessIds(ctypes.Structure):
        _fields_ = [("assigned", ctypes.c_uint), ("count", ctypes.c_uint),
                    ("ids", ctypes.c_size_t * 64)]

    kernel = lifecycle._get_kernel()
    kernel.QueryInformationJobObject.argtypes = [lifecycle._JobHandle, ctypes.c_int,
                                                ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
    kernel.QueryInformationJobObject.restype = ctypes.c_int
    kernel.WaitForSingleObject.argtypes = [lifecycle._JobHandle, ctypes.c_uint]
    kernel.WaitForSingleObject.restype = ctypes.c_uint
    root = subprocess.Popen(
        ["cmd", "/d", "/c", "ping -n 2 127.0.0.1 >nul & start /b ping -n 30 127.0.0.1 >nul"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    job = lifecycle.create_translation_job(root)
    descendants = []
    try:
        assert job is not None
        root.wait(timeout=10)
        ids = ProcessIds()
        assert kernel.QueryInformationJobObject(job.handle, 3, ctypes.byref(ids), ctypes.sizeof(ids), None)
        assert 0 < ids.count <= 64
        for pid in ids.ids[:ids.count]:
            assert pid != root.pid
            handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
            assert handle
            descendants.append(handle)
            assert kernel.WaitForSingleObject(handle, 0) == 258  # still alive
        context = translator.TranslationContext({}, "orphan-stop")
        context.process = root
        context.process_job = job
        asyncio.run(context.stop())
        assert job.handle is None
        for handle in descendants:
            assert kernel.WaitForSingleObject(handle, 5000) == 0
    finally:
        if job is not None:
            job.close(terminate=True)
        if root.poll() is None:
            root.kill()
            root.wait(timeout=5)
        for handle in descendants:
            kernel.CloseHandle(handle)
