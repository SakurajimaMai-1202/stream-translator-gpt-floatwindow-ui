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


@pytest.mark.parametrize('initial,expected_opens', [('finite', 1), ('live', 3), ('unknown', 2)])
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
    for _ in range(expected_opens):
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
    assert output.get() is AUDIO_STREAM_GAP
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
    assert output.get() is AUDIO_STREAM_GAP
    assert output.get() is None


@pytest.mark.parametrize('status', ['live', 'unknown'])
@pytest.mark.parametrize('failure', [FileNotFoundError('missing executable'), RuntimeError('Unsupported URL')])
def test_permanent_open_error_raises(monkeypatch, status, failure, capsys):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    monkeypatch.setattr(getter, '_source_status', lambda: status)
    def fail(*args):
        raise failure
    monkeypatch.setattr(audio_getter, '_open_stream', fail)
    with pytest.raises(RuntimeError, match='串流設定錯誤'):
        getter.loop(queue.SimpleQueue())
    assert '串流設定錯誤' in capsys.readouterr().out


def test_unsupported_url_stderr_is_fatal(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    monkeypatch.setattr(getter, '_source_status', lambda: 'unknown')
    failed = SimpleNamespace(poll=lambda: 1, _stderr_tail=b'ERROR: Unsupported URL: https://secret')
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *args: (failed, None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    with pytest.raises(RuntimeError, match='網址無效') as error:
        getter.loop(queue.SimpleQueue())
    assert 'secret' not in str(error.value)


@pytest.mark.parametrize('message', ['connection reset', 'HTTP Error 503', 'generic EOF'])
def test_transient_connection_errors_keep_retrying(monkeypatch, message):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    monkeypatch.setattr(getter, '_source_status', lambda: 'live')
    attempts = []
    def fail(*args):
        attempts.append(True)
        if len(attempts) == 8:
            getter.stop()
        raise RuntimeError(message)
    monkeypatch.setattr(audio_getter, '_open_stream', fail)
    getter.loop(queue.SimpleQueue())
    assert len(attempts) == 8


@pytest.mark.parametrize('delivered_audio', [False, True])
def test_repeated_ambiguous_error_cap_only_before_first_audio(monkeypatch, delivered_audio):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    monkeypatch.setattr(getter, '_source_status', lambda: 'live')
    attempts = []
    def open_stream(*args):
        attempts.append(True)
        if delivered_audio and len(attempts) == 1:
            return None, None
        if len(attempts) == 9:
            getter.stop()
        raise RuntimeError('Unable to extract audio format')
    monkeypatch.setattr(audio_getter, '_open_stream', open_stream)
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter([b'\0' * getter.byte_size]))
    if delivered_audio:
        getter.loop(queue.SimpleQueue())
        assert len(attempts) == 9
    else:
        with pytest.raises(RuntimeError, match='串流設定錯誤'):
            getter.loop(queue.SimpleQueue())
        assert len(attempts) == 5


def test_metadata_permanent_error_is_fatal(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    monkeypatch.setattr(audio_getter, '_build_ytdlp_command', lambda *a, **kw: ['yt-dlp'])
    monkeypatch.setattr(audio_getter.subprocess, 'run', lambda *a, **kw:
                        SimpleNamespace(returncode=1, stdout='', stderr='HTTP Error 403: Forbidden'))
    with pytest.raises(RuntimeError, match='串流設定錯誤'):
        getter.loop(queue.SimpleQueue())


def test_stderr_is_drained_with_bounded_tail():
    process = SimpleNamespace(stderr=io.BytesIO(b'x' * 20000 + b'Unsupported URL'))
    audio_getter._capture_stream_stderr(process)
    process._stderr_thread.join(timeout=2)
    assert not process._stderr_thread.is_alive()
    assert len(process._stderr_tail) == 8192
    assert process._stderr_tail.endswith(b'Unsupported URL')


@pytest.mark.parametrize('message', [
    'No module named yt_dlp', 'Requested format is not available',
    'HTTP Error 404: Not Found', 'This video is private',
    'members-only content', 'Sign in to confirm your age', 'Invalid URL',
])
def test_explicit_permanent_error_patterns(message):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    with pytest.raises(RuntimeError, match='串流設定錯誤'):
        getter._check_stream_error(message)


def test_missing_cookies_is_ignored_with_warning(tmp_path, capsys):
    # Public streams still work without cookies; a stale path must not block them.
    assert audio_getter._resolve_cookie_file('https://example.com/live', str(tmp_path / 'missing.txt')) is None
    assert 'Cookies' in capsys.readouterr().out


def test_permanent_error_after_audio_keeps_reconnecting():
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    getter._received_audio = True
    getter._check_stream_error('ERROR: HTTP Error 403: Forbidden')


def test_different_or_transient_errors_reset_startup_cap():
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    for _ in range(4):
        getter._check_stream_error('Unable to extract audio')
    getter._check_stream_error('HTTP Error 503')
    for _ in range(4):
        getter._check_stream_error('Unable to extract audio')
    getter._check_stream_error('Unable to extract different audio')
    assert getter._startup_failures == 1


@pytest.mark.parametrize('initial', ['unknown'])
def test_permanently_unknown_eof_is_bounded(monkeypatch, initial):
    getter = audio_getter.StreamAudioGetter('https://example.com/video', 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    calls = []
    def status():
        calls.append(True)
        assert len(calls) <= 1 + getter.MAX_UNKNOWN_EOF_CHECKS
        getter._metadata_answered = True
        return initial if len(calls) == 1 else 'unknown'
    monkeypatch.setattr(getter, '_source_status', status)
    opens = []
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (opens.append(True), None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    output = queue.SimpleQueue()
    getter.loop(output)
    assert len(opens) == 1
    assert len(calls) == 1 + getter.MAX_UNKNOWN_EOF_CHECKS
    assert output.get_nowait() is AUDIO_STREAM_GAP
    assert output.get_nowait() is None
    assert output.empty()


def test_eof_gap_precedes_cleanup_and_metadata(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    output = queue.SimpleQueue()
    calls = []
    def status():
        calls.append(True)
        if len(calls) == 1:
            return 'live'
        # Represents a slow metadata provider: speech must already be flushed.
        assert output.get_nowait() is AUDIO_STREAM_GAP
        return 'ended'
    monkeypatch.setattr(getter, '_source_status', status)
    monkeypatch.setattr(audio_getter, '_open_stream', lambda *a: (None, None))
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    def close():
        assert not output.empty()
    monkeypatch.setattr(getter, '_close_stream', close)
    getter.loop(output)
    assert output.get_nowait() is None
    assert output.empty()


@pytest.mark.parametrize('message', ['[https @ 000001] HTTP error 404 Not Found', 'Server returned 403 Forbidden'])
def test_ffmpeg_403_404_must_repeat_before_giving_up(message):
    # A live playlist can 404 briefly before it is ready; only yt-dlp's own
    # "HTTP Error 403:" line is definite.
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    for _ in range(4):
        getter._check_stream_error(message)
    with pytest.raises(RuntimeError, match='串流設定錯誤'):
        getter._check_stream_error(message)


def test_ffmpeg_denial_with_changing_pointers_still_gives_up():
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    for attempt in range(4):
        getter._check_stream_error(f'[https @ 00000{attempt}a1b3c4d5e0] HTTP error 403 Forbidden')
    with pytest.raises(RuntimeError, match='403'):
        getter._check_stream_error('[https @ 0000099999999] Server returned 403 Forbidden (access denied)')
