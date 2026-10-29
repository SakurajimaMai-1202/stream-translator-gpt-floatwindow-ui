import asyncio
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import hardware_detector as hd


OLD = hd.GpuDevice(0, "Old GPU", "nvidia", "cuda")
NEW = hd.GpuDevice(0, "New GPU", "nvidia", "cuda")


@pytest.fixture(autouse=True)
def reset_cache(monkeypatch):
    monkeypatch.setattr(hd, "_GPU_CACHE", None)
    monkeypatch.setattr(hd, "_GPU_PROBE", None)
    for name in ("detect_runtime_python_gpus", "detect_torch_gpus",
                 "detect_windows_dxgi_adapters", "detect_nvidia_smi_gpus",
                 "detect_windows_video_controllers"):
        monkeypatch.setattr(hd, name, lambda: [])
    yield
    with hd._GPU_CACHE_LOCK:
        probe = hd._GPU_PROBE
    if probe is not None:
        probe.result(timeout=5)


def blocking_probe(monkeypatch, *, raises=False):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def probe():
        calls.append(1)
        entered.set()
        assert release.wait(5), "Probe was not released"
        if raises:
            raise ValueError("probe failed")
        return [NEW]

    monkeypatch.setattr(hd, "detect_runtime_python_gpus", probe)
    return entered, release, calls


def observe_waiters(monkeypatch, count):
    waiting = threading.Event()
    lock = threading.Lock()
    calls = []

    class ObservedFuture(Future):
        def result(self, timeout=None):
            with lock:
                calls.append(1)
                if len(calls) >= count:
                    waiting.set()
            return super().result(timeout)

    monkeypatch.setattr(hd, "Future", ObservedFuture)
    return waiting


def test_fresh_cache_hit(monkeypatch):
    calls = []
    monkeypatch.setattr(hd, "detect_runtime_python_gpus", lambda: calls.append(1) or [NEW])
    assert hd.detect_gpus() == [NEW]
    result = hd.detect_gpus()
    result.clear()
    assert hd.detect_gpus() == [NEW]
    assert calls == [1]


def test_stale_returns_immediately_and_refreshes_once(monkeypatch):
    age = (hd.GPU_CACHE_TTL_SECONDS + hd.GPU_CACHE_MAX_STALE_SECONDS) / 2
    hd._GPU_CACHE = (time.monotonic() - age, (OLD,))
    entered, release, calls = blocking_probe(monkeypatch)
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = [pool.submit(hd.detect_gpus) for _ in range(6)]
            assert all(result.result(timeout=2) == [OLD] for result in results)
        assert entered.wait(2)
        assert calls == [1]
        probe = hd._GPU_PROBE
    finally:
        release.set()
    assert probe.result(timeout=2) == (NEW,)
    assert hd.detect_gpus() == [NEW]
    assert calls == [1]


@pytest.mark.parametrize("background_probe", [False, True])
def test_cache_older_than_max_age_waits_for_shared_probe(monkeypatch, background_probe):
    waiting = observe_waiters(monkeypatch, 3 if not background_probe else 4)
    entered, release, calls = blocking_probe(monkeypatch)
    with ThreadPoolExecutor(max_workers=4) as pool:
        try:
            if background_probe:
                hd._GPU_CACHE = (time.monotonic() - hd.GPU_CACHE_TTL_SECONDS - 1, (OLD,))
                assert hd.detect_gpus() == [OLD]
                assert entered.wait(2)
            with hd._GPU_CACHE_LOCK:
                hd._GPU_CACHE = (time.monotonic() - hd.GPU_CACHE_MAX_STALE_SECONDS - 1, (OLD,))
            results = [pool.submit(hd.detect_gpus) for _ in range(4)]
            assert entered.wait(2)
            assert waiting.wait(2)
            assert all(not result.done() for result in results)
            assert calls == [1]
        finally:
            release.set()
        assert all(result.result(timeout=2) == [NEW] for result in results)
    assert calls == [1]
    assert hd.detect_gpus() == [NEW]


@pytest.mark.parametrize("force_refresh", [False, True])
@pytest.mark.parametrize("raises", [False, True])
def test_concurrent_callers_share_result_or_exception(monkeypatch, force_refresh, raises):
    waiting = observe_waiters(monkeypatch, 3)
    entered, release, calls = blocking_probe(monkeypatch, raises=raises)
    with ThreadPoolExecutor(max_workers=4) as pool:
        owner = pool.submit(hd.detect_gpus)
        try:
            assert entered.wait(2)
            waiters = [pool.submit(hd.detect_gpus, force_refresh=force_refresh) for _ in range(3)]
            assert waiting.wait(2)
            assert calls == [1]
        finally:
            release.set()
        for result in [owner, *waiters]:
            if raises:
                with pytest.raises(ValueError, match="probe failed"):
                    result.result(timeout=2)
            else:
                assert result.result(timeout=2) == [NEW]
    assert hd._GPU_PROBE is None
    if raises:
        assert hd._GPU_CACHE is None
        with pytest.raises(ValueError, match="probe failed"):
            hd.detect_gpus()
        assert calls == [1, 1]


def test_failed_refresh_preserves_stale_cache(monkeypatch):
    cached = (time.monotonic() - hd.GPU_CACHE_TTL_SECONDS - 1, (OLD,))
    hd._GPU_CACHE = cached
    entered, release, calls = blocking_probe(monkeypatch, raises=True)
    try:
        assert hd.detect_gpus() == [OLD]
        assert entered.wait(2)
        probe = hd._GPU_PROBE
    finally:
        release.set()
    with pytest.raises(ValueError, match="probe failed"):
        probe.result(timeout=2)
    assert hd._GPU_CACHE == cached
    assert hd._GPU_PROBE is None


def test_force_refresh_replaces_fresh_cache(monkeypatch):
    hd._GPU_CACHE = (time.monotonic(), (OLD,))
    monkeypatch.setattr(hd, "detect_runtime_python_gpus", lambda: [NEW])
    assert hd.detect_gpus(force_refresh=True) == [NEW]
    assert hd.detect_gpus() == [NEW]


def test_force_refresh_joins_background_probe(monkeypatch):
    hd._GPU_CACHE = (time.monotonic() - hd.GPU_CACHE_TTL_SECONDS - 1, (OLD,))
    waiting = observe_waiters(monkeypatch, 1)
    entered, release, calls = blocking_probe(monkeypatch)
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            assert hd.detect_gpus() == [OLD]
            assert entered.wait(2)
            result = pool.submit(hd.detect_gpus, force_refresh=True)
            assert waiting.wait(2)
            assert not result.done()
            assert calls == [1]
        finally:
            release.set()
        assert result.result(timeout=2) == [NEW]
    assert calls == [1]


def test_without_windows_fallback_bypasses_cache(monkeypatch):
    cached = (time.monotonic(), (OLD,))
    hd._GPU_CACHE = cached
    calls = []
    monkeypatch.setattr(hd, "detect_torch_gpus", lambda: calls.append(1) or [NEW])
    assert hd.detect_gpus(False) == [NEW]
    assert hd.detect_gpus(False, force_refresh=True) == [NEW]
    assert calls == [1, 1]
    assert hd._GPU_CACHE == cached


def test_lifespan_skips_runtime_warmup(monkeypatch):
    from backend import main
    from backend.api import llama
    from backend.core import translator

    async def no_probe():
        pass

    monkeypatch.setenv("FLOATWINDOW_SKIP_RUNTIME_WARMUP", "1")
    monkeypatch.setattr(llama, "probe_existing_llama_server", no_probe)
    monkeypatch.setattr(main, "_start_public_server", lambda: None)
    monkeypatch.setattr(translator, "active_translations", {})

    def unexpected_thread(*args, **kwargs):
        pytest.fail("Warm-up must not create a thread")

    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=unexpected_thread))

    async def run():
        async with main.lifespan(main.app):
            pass

    asyncio.run(run())


def test_runtime_warmup_probes_in_daemon_thread(monkeypatch):
    from backend import main

    started = []
    calls = []

    class FakeThread:
        def __init__(self, target, daemon, name):
            self.target, self.daemon = target, daemon

        def start(self):
            started.append(self.daemon)
            self.target()

    monkeypatch.delenv("FLOATWINDOW_SKIP_RUNTIME_WARMUP", raising=False)
    monkeypatch.setattr(main, "threading", SimpleNamespace(Thread=FakeThread))
    monkeypatch.setattr(hd, "detect_gpus", lambda: calls.append(1) or [NEW])
    main._start_runtime_warmup()
    assert started == [True]
    assert calls == [1]


@pytest.mark.parametrize("refresh", [False, True])
def test_runtime_status_refresh_query(monkeypatch, refresh):
    from backend.api import runtime

    config = {"runtime": {"profile": "cpu"}}
    calls = []
    builds = []
    monkeypatch.setattr(runtime, "get_config_manager", lambda: SimpleNamespace(get_config=lambda: config))
    monkeypatch.setattr(runtime, "detect_gpus", lambda **kwargs: calls.append(kwargs) or [NEW])

    def build(*args):
        builds.append(args)
        return {"devices": []}

    monkeypatch.setattr(runtime, "build_runtime_status", build)
    app = FastAPI()
    app.include_router(runtime.router, prefix="/api")
    with TestClient(app) as client:
        response = client.get("/api/runtime/status" + ("?refresh=true" if refresh else ""))
    assert response.status_code == 200
    assert calls == ([{"force_refresh": True}] if refresh else [])
    assert builds == ([(config, [NEW])] if refresh else [(config,)])
