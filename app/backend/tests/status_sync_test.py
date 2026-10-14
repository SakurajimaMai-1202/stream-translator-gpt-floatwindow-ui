"""Status events retain endpoint shapes and cannot interrupt jobs."""
import asyncio
import threading
from datetime import datetime

import pytest

from backend.core import app_sync
from backend.core.app_update_manager import AppUpdateManager
from backend.core.cpu_asr_sidecar_manager import CpuAsrSidecarManager
from backend.core.llama_runtime_installer import LlamaRuntimeInstaller
from backend.core.model_download_manager import ModelDownloadManager
from backend.models.model_download import ModelDownloadTask, ModelDownloadTaskListResponse


@pytest.mark.parametrize('factory,event,field,envelope', [
    (AppUpdateManager, 'app_update.status', 'status', True),
    (CpuAsrSidecarManager, 'cpu_asr_sidecar.status', 'status', True),
    (LlamaRuntimeInstaller, 'llama_runtime.install_status', 'state', False),
])
def test_status_event_matches_get_payload(monkeypatch, factory, event, field, envelope):
    published = []
    monkeypatch.setattr(app_sync.broker, 'publish_status', lambda name, payload: published.append((name, payload)))
    manager = factory()
    manager._set(**{field: 'downloading', 'progress': 0.1})
    manager._set(**{field: 'completed', 'progress': 1.0})
    expected = {'success': True, 'data': manager.status()} if envelope else manager.status()
    assert published[-1] == (event, expected)
    previous = published[-2][1]['data'] if envelope else published[-2][1]
    assert previous[field] == 'downloading'


def test_model_task_event_matches_list_endpoint(monkeypatch):
    published = []
    monkeypatch.setattr(app_sync.broker, 'publish_status', lambda name, payload: published.append((name, payload)))
    manager = ModelDownloadManager()
    now = datetime.now()
    manager._tasks['job'] = ModelDownloadTask(task_id='job', engine='faster-whisper', model_id='tiny',
                                            status='pending', created_at=now, updated_at=now)
    manager._update_task('job', status='downloading', progress=0.5)
    manager._update_task('job', status='completed', progress=1.0)
    expected = ModelDownloadTaskListResponse(success=True, tasks=manager.list_tasks()).model_dump(mode='json')
    assert published[-1] == ('model_download.status', expected)


def test_progress_throttle_and_final_state(monkeypatch):
    published = []
    clock = [10.0]
    monkeypatch.setattr(app_sync.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(app_sync.broker, 'publish_status', lambda name, payload: published.append(payload))
    publisher = app_sync.StatusPublisher('status')
    for progress in range(10):
        publisher.publish(lambda: {'progress': progress}, key='job', state='downloading')
    assert published == [{'progress': 0}]
    clock[0] += 0.25
    publisher.publish(lambda: {'progress': 10}, key='job', state='downloading')
    publisher.publish(lambda: {'progress': 1.0}, key='job', state='completed')
    assert published[-1] == {'progress': 1.0}
    assert len(published) == 3


def test_publish_failure_does_not_break_install_job(monkeypatch):
    def fail(*args):
        raise RuntimeError('stream unavailable')
    monkeypatch.setattr(app_sync.broker, 'publish_status', fail)
    manager = LlamaRuntimeInstaller()
    job = manager.begin('cpu')
    monkeypatch.setattr('backend.core.llama_runtime_installer.list_latest_variants', lambda *args: {
        'tag': 'test', 'variants': [{'id': 'cpu', 'assets': []}]})
    monkeypatch.setattr(manager, '_download_and_install', lambda *args: 'runtime/llama-server.exe')
    asyncio.run(manager.install(job, 'cpu', 'cpu'))
    assert manager.status()['state'] == 'completed'


def test_thread_publication_uses_subscriber_loop_and_exact_payload():
    async def run():
        broker = app_sync.AppSyncBroker()
        queue = await broker.subscribe()
        thread = threading.Thread(target=broker.publish_status, args=('status', {'progress': 0.5}))
        thread.start()
        await asyncio.to_thread(thread.join)
        event = await asyncio.wait_for(queue.get(), timeout=1)
        assert event == {'type': 'status', 'payload': {'progress': 0.5}}
        await broker.unsubscribe(queue)
    asyncio.run(run())


@pytest.mark.parametrize('factory,field', [
    (AppUpdateManager, 'status'),
    (CpuAsrSidecarManager, 'status'),
    (LlamaRuntimeInstaller, 'state'),
])
def test_manager_progress_is_throttled_but_terminal_is_delivered(monkeypatch, factory, field):
    published = []
    monkeypatch.setattr(app_sync.time, 'monotonic', lambda: 10.0)
    monkeypatch.setattr(app_sync.broker, 'publish_status', lambda name, payload: published.append(payload))
    manager = factory()
    published.clear()
    manager._set(**{field: 'downloading', 'progress': 0.1})
    manager._set(progress=0.2)
    manager._set(progress=0.3)
    assert len(published) == 1
    manager._set(**{field: 'completed', 'progress': 1.0})
    assert len(published) == 2
    payload = published[-1].get('data', published[-1])
    assert payload[field] == 'completed'
    assert payload['progress'] == 1.0


def test_other_jobs_continue_when_publication_fails(monkeypatch):
    def fail(*args):
        raise RuntimeError('disconnected')
    monkeypatch.setattr(app_sync.broker, 'publish_status', fail)
    for manager in (AppUpdateManager(), CpuAsrSidecarManager()):
        manager._set(status='downloading', progress=0.5)
        manager._set(status='completed', progress=1.0)
        assert manager.status()['status'] == 'completed'
    manager = ModelDownloadManager()
    now = datetime.now()
    manager._tasks['job'] = ModelDownloadTask(task_id='job', engine='faster-whisper', model_id='tiny',
                                            status='pending', created_at=now, updated_at=now)
    manager._update_task('job', status='downloading', progress=0.5)
    manager._update_task('job', status='completed', progress=1.0)
    assert manager.get_task('job').status == 'completed'
