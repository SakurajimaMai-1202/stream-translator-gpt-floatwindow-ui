import asyncio

import pytest

from backend.core.model_download_manager import ModelDownloadManager


def test_cancel_transitions_active_task_without_completion(monkeypatch):
    asyncio.run(_cancel_transitions_active_task_without_completion(monkeypatch))


async def _cancel_transitions_active_task_without_completion(monkeypatch):
    manager = ModelDownloadManager()
    entered = asyncio.Event()

    async def blocked_download(task_id, model_id, cancel_event):
        entered.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise asyncio.CancelledError

    monkeypatch.setattr(manager, "_download_sherpa_archive", blocked_download)
    task_id = await manager.start_download(
        "sensevoice", "iic/SenseVoiceSmall", "cpu"
    )
    await asyncio.wait_for(entered.wait(), timeout=1)

    cancelling = manager.cancel(task_id)
    assert cancelling.status == "cancelling"
    for _ in range(100):
        current = manager.get_task(task_id)
        if current and current.status == "cancelled":
            break
        await asyncio.sleep(0.01)

    current = manager.get_task(task_id)
    assert current is not None
    assert current.status == "cancelled"
    assert current.progress < 1


def test_cancel_is_idempotent_for_finished_task(monkeypatch):
    asyncio.run(_cancel_is_idempotent_for_finished_task(monkeypatch))


async def _cancel_is_idempotent_for_finished_task(monkeypatch):
    manager = ModelDownloadManager()

    async def completed_download(task_id, model_id, cancel_event):
        return None

    monkeypatch.setattr(manager, "_download_sherpa_archive", completed_download)
    task_id = await manager.start_download(
        "sensevoice", "iic/SenseVoiceSmall", "cpu"
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    result = manager.cancel(task_id)
    assert result.status == "completed"


def test_cancel_unknown_task_is_not_silently_accepted():
    manager = ModelDownloadManager()
    with pytest.raises(KeyError):
        manager.cancel("missing")


async def _wait_until(predicate):
    for _ in range(200):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("Download did not stop promptly")


@pytest.mark.parametrize("backend", ["gpu", "cpu"])
@pytest.mark.parametrize("prefetch_raises", [True, False])
def test_hf_cancel_stops_worker_and_blocks_restart(monkeypatch, tmp_path, backend, prefetch_raises):
    asyncio.run(_hf_cancel_stops_worker_and_blocks_restart(monkeypatch, tmp_path, backend, prefetch_raises))


async def _hf_cancel_stops_worker_and_blocks_restart(monkeypatch, tmp_path, backend, prefetch_raises):
    import sys
    from threading import Event
    from types import SimpleNamespace
    import backend.core.model_download_manager as module

    monkeypatch.setattr(module, "WORKER_STOP_TIMEOUT_SECONDS", 0.2)
    manager = ModelDownloadManager()
    entered, stopping, release, exited = (Event() for _ in range(4))
    snapshots = []

    def prefetch(repo_id, info, cache_dir, allow_file=lambda _: True, *, cancel_event=None):
        assert cancel_event is not None
        entered.set()
        try:
            assert cancel_event.wait(2)
            stopping.set()
            assert release.wait(2)
            if prefetch_raises:
                raise InterruptedError("Download cancelled")
        finally:
            exited.set()

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(
        HfApi=lambda: SimpleNamespace(model_info=lambda *args, **kwargs: SimpleNamespace(siblings=[])),
        snapshot_download=lambda **kwargs: snapshots.append(kwargs),
    ))
    monkeypatch.setattr(module, "get_huggingface_hub_cache", lambda: tmp_path / "hub")
    monkeypatch.setattr(module, "ensure_model_storage", lambda: tmp_path)
    monkeypatch.setattr(module, "prefetch_large_files", prefetch)
    task_id = await manager.start_download("qwen3-asr", "Qwen/Qwen3-ASR-1.7B", backend)
    try:
        await _wait_until(entered.is_set)
        assert manager.cancel(task_id).status == "cancelling"
        await _wait_until(stopping.is_set)
        with pytest.raises(ValueError, match="上一次下載仍在停止中，請稍後再試"):
            await manager.start_download("qwen3-asr", "Qwen/Qwen3-ASR-1.7B", backend)
        assert not manager._workers[task_id].done()
        assert not exited.is_set()
        assert len(manager.list_tasks()) == 1
        manager._update_task(task_id, status="completed", progress=1, message="late")
        assert manager.get_task(task_id).status == "cancelling"
    finally:
        manager.cancel(task_id)
        release.set()
    await _wait_until(lambda: manager.get_task(task_id).status == "cancelled")
    assert exited.is_set()
    assert not snapshots
    cancelled = manager.get_task(task_id)
    manager._update_task(task_id, status="completed", progress=1, message="late")
    manager._update_task(task_id, status="failed", error="late error")
    manager._update_task(task_id, progress=0.9, message="late progress")
    assert manager.get_task(task_id) == cancelled

    # Once the old thread exits, its callbacks must not affect a new task.
    fresh_entered = asyncio.Event()

    async def fresh_download(task_id, model_id, cancel_event):
        fresh_entered.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise InterruptedError("Download cancelled")

    monkeypatch.setattr(manager, "_download_from_hf", fresh_download)
    monkeypatch.setattr(manager, "_download_sherpa_archive", fresh_download)
    fresh_id = await manager.start_download("qwen3-asr", "Qwen/Qwen3-ASR-1.7B", backend)
    await asyncio.wait_for(fresh_entered.wait(), timeout=1)
    fresh = manager.get_task(fresh_id)
    manager._update_task(task_id, status="completed", progress=1)
    assert manager.get_task(fresh_id) == fresh
    manager.cancel(fresh_id)
    await _wait_until(lambda: manager.get_task(fresh_id).status == "cancelled")


def test_cancel_terminates_sdk_process(monkeypatch, tmp_path):
    asyncio.run(_cancel_terminates_sdk_process(monkeypatch, tmp_path))


async def _cancel_terminates_sdk_process(monkeypatch, tmp_path):
    import sys
    from threading import Event
    from types import SimpleNamespace
    import backend.core.model_download_manager as module

    manager = ModelDownloadManager()
    entered = Event()
    calls = []

    class Process:
        pid = 123456789
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            calls.append("kill")
            self.returncode = -9

        def wait(self, timeout):
            calls.append("wait")
            assert self.returncode is not None
            return self.returncode

    process = Process()

    def popen(*args, **kwargs):
        assert kwargs["stdout"] != module.subprocess.PIPE
        entered.set()
        return process

    def taskkill(command, **kwargs):
        assert command == ["taskkill", "/T", "/F", "/PID", str(process.pid)]
        calls.append("taskkill")
        process.kill()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.subprocess, "run", taskkill)
    if module.os.name != "nt":
        monkeypatch.setattr(module.os, "killpg", lambda pid, sig: process.kill())
    monkeypatch.setattr(module, "get_app_root", lambda: tmp_path)
    monkeypatch.setattr(manager, "_get_modelscope_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(manager, "_resolve_sensevoice_download_python", lambda event: sys.executable)
    task_id = await manager.start_download("sensevoice", "iic/SenseVoiceSmall")
    await _wait_until(entered.is_set)
    manager.cancel(task_id)
    await _wait_until(lambda: manager.get_task(task_id).status == "cancelled")
    assert "kill" in calls
    assert "wait" in calls
    if module.os.name == "nt":
        assert "taskkill" in calls


def test_cancel_before_worker_starts(monkeypatch):
    asyncio.run(_cancel_before_worker_starts(monkeypatch))


async def _cancel_before_worker_starts(monkeypatch):
    manager = ModelDownloadManager()

    async def unexpected_download(*args):
        pytest.fail("Cancelled task must not start downloading")

    monkeypatch.setattr(manager, "_download_from_hf", unexpected_download)
    task_id = await manager.start_download("faster-whisper", "tiny")
    manager.cancel(task_id)
    await _wait_until(lambda: manager.get_task(task_id).status == "cancelled")
    assert not manager._model_workers


def test_prefetch_propagates_cancel_without_sdk_fallback(monkeypatch, tmp_path):
    import sys
    from contextlib import nullcontext
    from threading import Event
    from types import SimpleNamespace
    import backend.core.hf_parallel_download as module

    cancel_event = Event()

    class Downloader:
        def __init__(self, *, cancel_event):
            self.event = cancel_event

        def download(self, url, partial):
            assert self.event is cancel_event
            partial.write_bytes(b"resumable")
            self.event.set()
            raise InterruptedError("Download cancelled")

    monkeypatch.setattr(module, "HttpDownloader", Downloader)
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(hf_hub_url=lambda *args, **kwargs: "fake"))
    monkeypatch.setitem(sys.modules, "huggingface_hub.utils", SimpleNamespace(
        WeakFileLock=lambda *args: nullcontext(), validate_repo_id=lambda repo_id: None,
    ))
    info = SimpleNamespace(sha="a" * 40, siblings=[SimpleNamespace(
        rfilename="model.bin", size=2 * module.DOWNLOAD_CHUNK_SIZE, lfs={"sha256": "b" * 64},
    )])
    with pytest.raises(InterruptedError):
        module.prefetch_large_files("org/model", info, tmp_path, cancel_event=cancel_event)
    partial = tmp_path / "models--org--model" / "blobs" / (("b" * 64) + ".incomplete")
    assert partial.read_bytes() == b"resumable"


def test_snapshot_checks_cancellation_after_native_call(monkeypatch):
    import sys
    from threading import Event
    from types import SimpleNamespace

    cancel_event = Event()
    calls = []

    def snapshot(**kwargs):
        calls.append(kwargs)
        cancel_event.set()
        return "snapshot"

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    with pytest.raises(InterruptedError, match="Download cancelled"):
        ModelDownloadManager()._snapshot_download(cancel_event, repo_id="test/model")
    assert calls == [{"repo_id": "test/model"}]


@pytest.mark.parametrize("cancel_probe", [True, False])
def test_sensevoice_probe_propagates_cancel_or_timeout(monkeypatch, tmp_path, cancel_probe):
    from threading import Event
    import backend.core.model_download_manager as module

    manager = ModelDownloadManager()
    cancel_event = Event()
    runtime = tmp_path / "_runtime" / "python.exe"
    runtime.parent.mkdir()
    runtime.touch()
    calls = []

    def probe(command, event, *, timeout):
        assert event is cancel_event
        assert timeout == 60
        calls.append(command)
        if cancel_probe:
            event.set()
            manager._check_cancelled(event)
        raise module.subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(module, "get_app_root", lambda: tmp_path)
    monkeypatch.setattr(manager, "_run_download_process", probe)
    error = InterruptedError if cancel_probe else module.subprocess.TimeoutExpired
    with pytest.raises(error):
        manager._resolve_sensevoice_download_python(cancel_event)
    assert calls == [[str(runtime), "-c", "import funasr"]]


def test_download_process_uses_requested_timeout(monkeypatch, tmp_path):
    from threading import Event
    from types import SimpleNamespace
    import backend.core.model_download_manager as module

    manager = ModelDownloadManager()
    process = SimpleNamespace(poll=lambda: None)
    stopped = []
    ticks = iter([0, 60])
    monkeypatch.setattr(module, "get_app_root", lambda: tmp_path)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(manager, "_stop_download_process", stopped.append)
    with pytest.raises(module.subprocess.TimeoutExpired) as error:
        manager._run_download_process(["python", "-c", "import funasr"], Event(), timeout=60)
    assert error.value.timeout == 60
    assert stopped == [process]


def test_restart_waits_for_cancelling_worker(monkeypatch):
    asyncio.run(_restart_waits_for_cancelling_worker(monkeypatch))


async def _restart_waits_for_cancelling_worker(monkeypatch):
    manager = ModelDownloadManager()
    entered = asyncio.Event()
    exited = asyncio.Event()
    running = set()
    starts = []

    async def download(task_id, model_id, cancel_event):
        assert not running
        if starts:
            assert exited.is_set()
        running.add(task_id)
        starts.append(task_id)
        entered.set()
        try:
            while not cancel_event.is_set():
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.5)
            raise InterruptedError("Download cancelled")
        finally:
            running.remove(task_id)
            exited.set()

    monkeypatch.setattr(manager, "_download_sherpa_archive", download)
    old_id = await manager.start_download("sensevoice", "iic/SenseVoiceSmall", "cpu")
    old_worker = manager._workers[old_id]
    await asyncio.wait_for(entered.wait(), timeout=1)
    manager.cancel(old_id)
    entered.clear()
    new_id = await manager.start_download("sensevoice", "iic/SenseVoiceSmall", "cpu")
    new_worker = manager._workers[new_id]
    try:
        assert old_worker.done()
        assert exited.is_set()
        assert manager.get_task(old_id).status == "cancelled"
        assert new_id != old_id
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert starts == [old_id, new_id]
        assert running == {new_id}
    finally:
        manager.cancel(new_id)
        await asyncio.wait_for(new_worker, timeout=2)


def test_live_download_is_not_duplicated(monkeypatch):
    asyncio.run(_live_download_is_not_duplicated(monkeypatch))


async def _live_download_is_not_duplicated(monkeypatch):
    manager = ModelDownloadManager()
    entered = asyncio.Event()

    async def download(task_id, repo_id, cancel_event):
        entered.set()
        while not cancel_event.is_set():
            await asyncio.sleep(0.01)
        raise InterruptedError("Download cancelled")

    monkeypatch.setattr(manager, "_download_from_hf", download)
    task_id = await manager.start_download("faster-whisper", "tiny")
    worker = manager._workers[task_id]
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        # The repo alias must claim the same backend model key.
        with pytest.raises(ValueError, match="上一次下載仍在停止中，請稍後再試"):
            await manager.start_download("faster-whisper", "Systran/faster-whisper-tiny")
        assert list(manager._workers) == [task_id]
        assert len(manager.list_tasks()) == 1
        assert not worker.done()
    finally:
        manager.cancel(task_id)
        await asyncio.wait_for(worker, timeout=1)


def test_dedicated_logger_uses_isolated_log_dir(isolated_log_dir):
    from pathlib import Path
    from backend.core.logging_setup import configure_dedicated_file_logger, resolve_log_dir

    assert resolve_log_dir() == isolated_log_dir
    logger = configure_dedicated_file_logger("test.download.isolated", "test_download")
    try:
        logger.warning("isolated download log")
        for handler in logger.handlers:
            handler.flush()
            assert Path(handler.baseFilename).parent == isolated_log_dir
        assert "isolated download log" in (isolated_log_dir / "test_download.log").read_text(encoding="utf-8")
    finally:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
