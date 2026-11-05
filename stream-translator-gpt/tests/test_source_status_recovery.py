"""Offline metadata failure and reconnect regressions."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AudioSourceQueue, FRAME_DURATION


@pytest.fixture
def source(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_getter.tempfile, 'mkdtemp', lambda: str(tmp_path / 'capture'))
    getter = audio_getter.StreamAudioGetter('https://example.com/video', 'ba', '', '')
    clock = SimpleNamespace(now=100.0, opens=0, calls=0)
    monkeypatch.setattr(audio_getter.time, 'monotonic', lambda: clock.now)
    monkeypatch.setattr(audio_getter, '_build_ytdlp_command', lambda *a, **kw: ['fake'])
    monkeypatch.setattr(audio_getter, '_resolve_ffmpeg_dir', lambda: None)
    monkeypatch.setattr(audio_getter, '_resolve_js_runtime_arg', lambda: None)

    def wait(delay):
        clock.now += delay
        return not getter.running

    getter._stop_event = SimpleNamespace(wait=wait, set=lambda: None)
    monkeypatch.setattr(getter, '_close_stream', lambda: None)

    def open_stream(*args):
        clock.opens += 1
        assert clock.opens < 30, 'unexpected unbounded reconnect'
        return None, None

    monkeypatch.setattr(audio_getter, '_open_stream', open_stream)
    monkeypatch.setattr(getter, '_read_stream_frames', lambda: iter(()))
    return getter, clock


def metadata(monkeypatch, getter, clock, answers, stop_after=None):
    answers = iter(answers)

    def run(*args, **kwargs):
        clock.calls += 1
        if stop_after is not None and clock.calls == stop_after:
            getter.stop()
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, dict):
            return SimpleNamespace(returncode=0, stdout=json.dumps(answer))
        if answer == 'nonzero':
            return SimpleNamespace(returncode=1, stdout='', stderr='connection reset')
        return SimpleNamespace(returncode=0, stdout=answer)

    monkeypatch.setattr(audio_getter.subprocess, 'run', run)


@pytest.mark.parametrize('failure', [
    'nonzero', 'broken JSON', '[]',
    audio_getter.subprocess.TimeoutExpired('fake', 15),
    OSError('network unavailable'),
])
def test_never_live_transport_failure_waits_until_stop(source, monkeypatch, failure, capsys):
    getter, clock = source
    count = getter.MAX_UNKNOWN_EOF_CHECKS + 5
    metadata(monkeypatch, getter, clock, [failure] * count, stop_after=count)
    output = AudioSourceQueue()
    getter.loop(output)
    assert clock.calls == count
    assert clock.opens == 1  # Do not replay a possible VOD while metadata is unavailable.
    assert 'Ending source' not in capsys.readouterr().out
    assert output.get() is audio_getter.AUDIO_STREAM_GAP
    assert output.get() is None


def test_successful_unknown_metadata_ends_with_reason(source, monkeypatch, capsys):
    getter, clock = source
    metadata(monkeypatch, getter, clock, [{}] * (getter.MAX_UNKNOWN_EOF_CHECKS + 1))
    output = AudioSourceQueue()
    getter.loop(output)
    assert clock.calls == getter.MAX_UNKNOWN_EOF_CHECKS + 1
    assert clock.opens == 1
    message = capsys.readouterr().out
    assert audio_getter.WARNING in message
    assert 'successful metadata checks returned no live flag' in message
    assert 'never confirmed live' in message
    assert output.get() is audio_getter.AUDIO_STREAM_GAP
    assert output.get() is None


@pytest.mark.parametrize('failure', ['nonzero', {}, 'broken JSON', audio_getter.subprocess.TimeoutExpired('fake', 15)])
@pytest.mark.parametrize('stall', [False, True])
def test_confirmed_live_wifi_drop_resumes_with_timeline(source, monkeypatch, stall, failure):
    getter, clock = source
    failures = getter.MAX_UNKNOWN_EOF_CHECKS + 2
    metadata(monkeypatch, getter, clock,
             [{'is_live': True}] + [failure] * failures + [{'live_status': 'post_live'}])

    def frames():
        if clock.opens == 1:
            yield b'\0' * getter.byte_size
            clock.now += 30
            if stall:
                raise TimeoutError('Wi-Fi dropped')
        elif clock.opens == failures + 1:
            clock.now += FRAME_DURATION
            yield b'\0' * getter.byte_size

    monkeypatch.setattr(getter, '_read_stream_frames', frames)
    output = AudioSourceQueue()
    getter.loop(output)
    items = [output.get_with_timeline() for _ in range(output.qsize())]
    audio = [(frame, advance) for frame, advance in items if isinstance(frame, np.ndarray)]
    assert clock.opens == failures + 1
    assert len(audio) == 2
    assert audio[0][1] == 0
    assert audio[1][1] == pytest.approx(30 + failures * getter.YOUTUBE_RECONNECT_DELAY_SECONDS)
    assert items[-1][0] is None


def test_startup_unknown_then_live_advances_reconnect(source, monkeypatch):
    getter, clock = source
    metadata(monkeypatch, getter, clock,
             ['nonzero', {'is_live': True}, {'live_status': 'post_live'}])

    def frames():
        clock.now += FRAME_DURATION
        yield b'\0' * getter.byte_size
        if clock.opens == 1:
            clock.now += 8
            raise TimeoutError('stalled')

    monkeypatch.setattr(getter, '_read_stream_frames', frames)
    output = AudioSourceQueue()
    getter.loop(output)
    items = [output.get_with_timeline() for _ in range(output.qsize())]
    advances = [advance for frame, advance in items if isinstance(frame, np.ndarray)]
    assert clock.opens == 2
    assert advances == pytest.approx([0, 8 + getter.YOUTUBE_RECONNECT_DELAY_SECONDS])


@pytest.mark.parametrize('failure', ['nonzero', audio_getter.subprocess.TimeoutExpired('fake', 15),
                                     OSError('network unavailable')])
def test_never_live_transport_failures_end_at_wall_clock_limit(source, monkeypatch, capsys, failure):
    getter, clock = source
    # Startup/reading time must not consume the post-EOF unknown budget.
    def frames():
        clock.now += getter.MAX_UNKNOWN_EOF_SECONDS * 2
        return iter(())

    monkeypatch.setattr(getter, '_read_stream_frames', frames)
    monkeypatch.setattr(getter, 'YOUTUBE_RECONNECT_DELAY_SECONDS', getter.MAX_UNKNOWN_EOF_SECONDS / 4)
    metadata(monkeypatch, getter, clock, [failure] * 6)
    output = AudioSourceQueue()
    getter.loop(output)
    assert clock.calls == 6  # Startup, first unknown, then four waits.
    assert clock.now == 100 + getter.MAX_UNKNOWN_EOF_SECONDS * 3
    assert clock.opens == 1
    message = capsys.readouterr().out
    assert f'{audio_getter.ERROR}Source status could not be confirmed' in message
    assert output.get() is audio_getter.AUDIO_STREAM_GAP
    assert output.get() is None
    assert output.empty()


def test_never_live_stall_reaching_wait_limit_raises(source, monkeypatch):
    getter, clock = source

    def frames():
        raise TimeoutError('stalled')

    monkeypatch.setattr(getter, '_read_stream_frames', frames)
    monkeypatch.setattr(getter, 'YOUTUBE_RECONNECT_DELAY_SECONDS', getter.MAX_UNKNOWN_EOF_SECONDS / 4)
    metadata(monkeypatch, getter, clock, ['nonzero'] * 6)
    # A mid-session stall that hits the wait limit is a failure, not a normal end.
    with pytest.raises(RuntimeError):
        getter.loop(AudioSourceQueue())


def test_confirmed_live_transport_failures_beyond_limit_wait_for_stop(source, monkeypatch, capsys):
    getter, clock = source
    monkeypatch.setattr(getter, 'YOUTUBE_RECONNECT_DELAY_SECONDS', getter.MAX_UNKNOWN_EOF_SECONDS / 2)
    metadata(monkeypatch, getter, clock, [{'is_live': True}] + ['nonzero'] * 6, stop_after=7)
    output = AudioSourceQueue()
    getter.loop(output)
    assert clock.now > 100 + getter.MAX_UNKNOWN_EOF_SECONDS
    assert clock.calls == 7
    assert clock.opens == 6
    assert not getter.running
    assert audio_getter.ERROR not in capsys.readouterr().out
    items = [output.get() for _ in range(output.qsize())]
    assert items[-1] is None


@pytest.mark.parametrize('stderr,reason', [
    ('ERROR: Twitter Space not found', '找不到這個 X Space（網址錯誤、已刪除或尚未公開）'),
    ('ERROR: Twitter Space ended and replay is disabled', 'X Space 已結束，且主持人沒有開放重播'),
])
def test_space_metadata_error_is_fatal_on_first_check(source, monkeypatch, stderr, reason):
    getter, clock = source
    def run(*args, **kwargs):
        clock.calls += 1
        return SimpleNamespace(returncode=1, stdout='', stderr=stderr + '\nUnable to extract')
    monkeypatch.setattr(audio_getter.subprocess, 'run', run)
    with pytest.raises(RuntimeError) as error:
        getter._source_status()
    assert reason in str(error.value)
    assert clock.calls == 1
    assert getter._startup_failures == 0
