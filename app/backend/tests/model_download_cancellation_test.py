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
