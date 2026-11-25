import io
import json
import queue
import re
from types import SimpleNamespace

import pytest

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AUDIO_STREAM_GAP


@pytest.mark.parametrize('url,expected', [
    ('https://tiktok.com/@creator/live', True),
    ('https://www.tiktok.com/@creator/live', True),
    ('https://m.tiktok.com/@creator/live', True),
    ('https://vt.tiktok.com/example', True),
    ('https://evil.com/tiktok.com/x', False),
    ('https://tiktok.com.evil.com/', False),
    ('not a URL', False),
    ('https://[invalid', False),
])
def test_is_tiktok_url(url, expected):
    assert audio_getter._is_tiktok_url(url) is expected


def _run_unknown_source_reconnects(monkeypatch, url, attempts, audio_passes=()):
    getter = audio_getter.StreamAudioGetter(url, 'ba', '', '')
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    monkeypatch.setattr(getter, '_source_status', lambda: 'unknown')
    wait_calls = []
    def wait(_delay):
        wait_calls.append(True)
        # Break the unknown-status poll, then allow the next outer attempt.
        return len(wait_calls) % 2 == 1
    monkeypatch.setattr(getter._stop_event, 'wait', wait)
    open_calls = []
    def open_stream(*_args):
        open_calls.append(True)
        if len(open_calls) > attempts:
            getter.running = False
            return None, None
        if len(open_calls) not in audio_passes:
            raise RuntimeError('connection reset')
        return None, None
    monkeypatch.setattr(audio_getter, '_open_stream', open_stream)
    monkeypatch.setattr(getter, '_read_stream_frames',
                        lambda: iter([b'\0' * getter.byte_size])
                        if len(open_calls) in audio_passes else iter(()))
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    getter.loop(queue.SimpleQueue())
    return open_calls


_TIKTOK_HINT = ('[WARNING] TikTok 目前常擋自動連線，網址模式可能一直連不上。'
                '建議改用「指定應用程式音訊」或「系統音訊」收瀏覽器播放的聲音。')
_RECONNECT_TEXTS = ('串流連線失敗，稍後重試：', '無法確認來源狀態，等待後重新確認…',
                    '來源尚未確認結束，正在重新連線…', '串流已連續 8 秒沒有音訊資料')


def _output(capsys):
    """(stdout lines, stderr lines) without the ANSI colour codes of the engine's prefixes."""
    captured = capsys.readouterr()
    plain = lambda text: [re.sub(r'\x1b\[[0-9;]*m', '', line) for line in text.splitlines()]
    return plain(captured.out), plain(captured.err)


def _notices(lines):
    return [line for line in lines if any(text in line for text in _RECONNECT_TEXTS)]


def _assert_hidden_notices_are_debug_on_stderr(out, err):
    # The UI only sees stdout [WARNING] lines; the backend logs stderr [DEBUG]
    # lines at debug level but drops [DEBUG] lines on stdout entirely.
    assert all(line.startswith('[WARNING] ') for line in _notices(out))
    hidden = _notices(err)
    assert hidden and all(line.startswith('[DEBUG] ') for line in hidden)


def test_tiktok_unknown_source_shows_hint_then_hides_reconnect_warnings(monkeypatch, capsys):
    _run_unknown_source_reconnects(monkeypatch, 'https://www.tiktok.com/@creator/live', 5)
    out, err = _output(capsys)
    # The hint itself must stay a visible [WARNING] line.
    assert out.count(_TIKTOK_HINT) == 1
    # Pass 1: failed open (1), failed status check (2) and the uncounted
    # reconnect notice are visible; pass 2's failed open is the 3rd attempt,
    # prints the hint and is hidden.
    assert len(_notices(out)) == 3
    assert out.index(_TIKTOK_HINT) > out.index(_notices(out)[-1])
    _assert_hidden_notices_are_debug_on_stderr(out, err)


def test_tiktok_stall_counts_once_per_pass(monkeypatch, capsys):
    getter = audio_getter.StreamAudioGetter('https://www.tiktok.com/@creator/live', 'ba', '', '')
    monkeypatch.setattr(getter, '_source_status', lambda: 'unknown')
    waits = []
    monkeypatch.setattr(getter._stop_event, 'wait', lambda _d: waits.append(True) or len(waits) % 2 == 1)
    opens = []

    def open_stream(*_args):
        opens.append(True)
        if len(opens) > 4:
            getter.running = False
        return None, None

    def stalled_read():
        raise TimeoutError('串流已連續 8 秒沒有音訊資料')
        yield  # pragma: no cover - makes this a generator

    monkeypatch.setattr(audio_getter, '_open_stream', open_stream)
    monkeypatch.setattr(getter, '_read_stream_frames', stalled_read)
    monkeypatch.setattr(getter, '_close_stream', lambda: None)
    getter.loop(queue.SimpleQueue())
    out, err = _output(capsys)
    # A stall must count once (not again after the try block): the stall and
    # the status check of pass 1 stay visible, the hint comes in pass 2.
    assert out.count(_TIKTOK_HINT) == 1
    assert [line.split('] ', 1)[1] for line in _notices(out)] == [
        '串流已連續 8 秒沒有音訊資料', '無法確認來源狀態，等待後重新確認…', '來源尚未確認結束，正在重新連線…']
    _assert_hidden_notices_are_debug_on_stderr(out, err)


def test_non_tiktok_unknown_source_keeps_reconnect_warnings(monkeypatch, capsys):
    _run_unknown_source_reconnects(monkeypatch, 'https://www.youtube.com/live/example', 5)
    out, err = _output(capsys)
    assert not any('TikTok 目前常擋自動連線' in line for line in out + err)
    assert len(_notices(out)) == 15  # 5 passes x (open failure, status check, reconnect)
    assert all(line.startswith('[WARNING] ') for line in _notices(out))
    assert not _notices(err)


def test_tiktok_audio_rearms_hint_and_reconnect_warnings(monkeypatch, capsys):
    _run_unknown_source_reconnects(
        monkeypatch, 'https://www.tiktok.com/@creator/live', 7, audio_passes=(4,))
    out, err = _output(capsys)
    assert out.count(_TIKTOK_HINT) == 2
    audio_pass = [i for i, line in enumerate(out) if 'Opening stream:' in line][3]
    before, after = out[:audio_pass], out[audio_pass:]
    assert before.count(_TIKTOK_HINT) == 1 and after.count(_TIKTOK_HINT) == 1
    # After audio the count restarts: status check (1), reconnect, failed open
    # (2) are visible; the next status check is the 3rd and brings the hint.
    assert len(_notices(after)) == 3
    assert after.index(_TIKTOK_HINT) > after.index(_notices(after)[-1])
    _assert_hidden_notices_are_debug_on_stderr(out, err)


def test_metadata_ytdlp_command_omits_download_options_and_keeps_shared_options(monkeypatch, tmp_path):
    cookies = tmp_path / 'cookies.txt'
    cookies.write_text('cookie data')
    monkeypatch.setattr(audio_getter, '_resolve_ytdlp_command', lambda: ['yt-dlp'])

    cmd = audio_getter._build_ytdlp_command(
        'https://www.youtube.com/live/example', 'bestaudio', str(cookies), 'http://proxy:8080',
        ffmpeg_dir='C:/ffmpeg/bin', js_runtime_arg='node:C:/node/node.exe', metadata=True)

    for option in ('-o', '-f', '--downloader-args', '--fragment-retries'):
        assert option not in cmd
    assert '--dump-single-json' in cmd
    assert '--skip-download' in cmd
    assert '--cookies' in cmd
    assert str(cookies) in cmd
    assert '--proxy' in cmd
    assert 'http://proxy:8080' in cmd
    assert '--ffmpeg-location' in cmd
    assert 'C:/ffmpeg/bin' in cmd
    assert '--js-runtimes' in cmd
    assert 'node:C:/node/node.exe' in cmd
    assert '--remote-components' in cmd
    assert 'ejs:github' in cmd


def test_download_ytdlp_command_is_unchanged(monkeypatch):
    monkeypatch.setattr(audio_getter, '_resolve_ytdlp_command', lambda: ['yt-dlp'])
    assert audio_getter._build_ytdlp_command(
        'https://example.com/live', 'bestaudio', '', '') == [
            'yt-dlp', 'https://example.com/live', '-f', 'bestaudio', '-o', '-', '-q',
            '--downloader-args', 'ffmpeg:-loglevel error',
        ]

def test_metadata_ytdlp_command_keeps_x_workaround_without_download_retries(monkeypatch):
    monkeypatch.setattr(audio_getter, '_resolve_ytdlp_command', lambda: ['yt-dlp'])
    x_cmd = audio_getter._build_ytdlp_command('https://x.com/i/spaces/1abcdefghijklm', 'ba', '', '', metadata=True)
    assert 'twitter:api=syndication' in x_cmd
    yt_cmd = audio_getter._build_ytdlp_command('https://www.youtube.com/live/example', 'ba', '', '', metadata=True)
    assert '--fragment-retries' not in yt_cmd and '--retry-sleep' not in yt_cmd


def test_source_status_reads_live_metadata_from_stdout_without_output_option(monkeypatch):
    getter = audio_getter.StreamAudioGetter('https://www.youtube.com/live/example', 'ba', '', '')
    monkeypatch.setattr(audio_getter, '_resolve_ytdlp_command', lambda: ['yt-dlp'])

    def run(cmd, **kwargs):
        assert '-o' not in cmd
        assert kwargs['encoding'] == 'utf-8'
        assert kwargs['errors'] == 'replace'
        return SimpleNamespace(returncode=0, stdout=json.dumps({'live_status': 'is_live'}), stderr='')

    monkeypatch.setattr(audio_getter.subprocess, 'run', run)
    assert getter._source_status() == 'live'


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


def test_login_message_beats_an_ffmpeg_403_in_the_same_tail():
    getter = audio_getter.StreamAudioGetter('https://example.com/live', 'ba', '', '')
    with pytest.raises(RuntimeError, match='登入'):
        getter._check_stream_error('Server returned 403 Forbidden\nERROR: Sign in to confirm your age')
