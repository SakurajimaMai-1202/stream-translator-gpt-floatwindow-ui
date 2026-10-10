import io
import json
import queue
from types import SimpleNamespace

import pytest

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AUDIO_STREAM_GAP


@pytest.mark.parametrize('metadata,expected', [
    ({'live_status': 'is_live'}, 'live'),
    ({'live_status': 'not_live'}, 'finite'),
    ({'live_status': 'post_live'}, 'ended'),
    ({'is_live': False}, 'finite'),
    ({}, 'unknown'),
])
def test_source_metadata_classification(monkeypatch, metadata, expected):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    monkeypatch.setattr(audio_getter, '_build_ytdlp_command', lambda *a, **kw: ['yt-dlp'])
    monkeypatch.setattr(audio_getter.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=0, stdout=json.dumps(metadata)))
    assert getter._source_status() == expected


@pytest.mark.parametrize('initial,expected_opens', [('finite', 1), ('live', 2), ('unknown', 2)])
def test_eof_retries_until_confirmed_end_but_never_replays_vod(monkeypatch, initial, expected_opens):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    statuses = iter([initial, 'unknown', 'live', 'ended'])
    monkeypatch.setattr(getter, '_source_status', lambda: next(statuses))
    opens = []
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (opens.append(True), None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    output = queue.SimpleQueue()
    getter.loop(output)
    assert len(opens) == expected_opens
    if expected_opens == 2:
        assert output.get() is AUDIO_STREAM_GAP
    assert output.get() is None


def test_reader_drains_pcm_after_process_exit():
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    pcm = b'\0' * getter.byte_size
    getter.ffmpeg_process = SimpleNamespace(stdout=io.BytesIO(pcm), poll=lambda: 0)
    assert list(getter._read_stream_frames()) == [pcm]
    getter.ffmpeg_process = None


def test_unknown_source_waits_for_metadata_without_reopening_vod(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/video', 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    statuses = iter(['unknown', 'unknown', 'finite'])
    monkeypatch.setattr(getter, '_source_status', lambda: next(statuses))
    opens = []
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (opens.append(True), None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    output = queue.SimpleQueue()
    getter.loop(output)
    assert len(opens) == 1
    assert output.get() is None


def test_finite_failed_transport_is_error_not_successful_eof(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/video', 'ba', '', '')
    monkeypatch.setattr(getter, '_source_status', lambda: 'finite')
    failed = SimpleNamespace(poll=lambda: 1)
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (failed, None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    with pytest.raises(RuntimeError, match='有限音訊來源讀取失敗'):
        getter.loop(queue.SimpleQueue())
    getter.ffmpeg_process = None


def test_manual_stop_ends_unknown_metadata_wait(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/video', 'ba', '', '')
    calls = []
    def status():
        calls.append(True)
        if len(calls) == 2:
            getter.stop()
        return 'unknown'
    monkeypatch.setattr(getter, '_source_status', status)
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (None, None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    output = queue.SimpleQueue()
    getter.loop(output)
    assert len(calls) == 2
    assert output.get() is None
