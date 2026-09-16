"""The subprocess stdout must carry each completed subtitle only once."""

import json
import queue

import numpy as np
import pytest

from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.result_exporter import ResultExporter, SUBTITLE_EVENT_PREFIX


@pytest.mark.parametrize("timestamps", [False, True])
@pytest.mark.parametrize("translation", ["你好", "你好\n大家好", ""])
@pytest.mark.parametrize("structured", [False, True])
def test_exporter_uses_one_stdout_format_and_preserves_delivery(
    capsys, timestamps, translation, structured
):
    task = TranslationTask(np.zeros(160, dtype=np.float32), (1.2346, 2.3456))
    task.transcript = "こんにちは"
    task.translation = translation
    task.llm_latency_ms = 12.0
    exporter = ResultExporter(
        cqhttp_url=None, cqhttp_token=None, discord_webhook_url=None,
        telegram_token=None, telegram_chat_id=None, output_file_path=None,
        proxy=None, output_whisper_result=True, output_timestamps=timestamps,
        show_latency_log=True, emit_json_events=structured,
    )
    # Capture delivery without starting network or file workers.
    exporter.file_queue = queue.SimpleQueue()
    exporter.subtitle_share_queue = queue.SimpleQueue()
    inputs = queue.SimpleQueue()
    inputs.put(task)
    inputs.put(None)

    exporter.loop(inputs)

    stdout = capsys.readouterr().out
    if structured:
        lines = stdout.splitlines()
        assert len(lines) == 1
        assert lines[0].startswith(SUBTITLE_EVENT_PREFIX)
        payload = json.loads(lines[0][len(SUBTITLE_EVENT_PREFIX):])
        assert payload["original"] == task.transcript
        assert payload["translated"] == translation
    else:
        assert SUBTITLE_EVENT_PREFIX not in stdout
        assert "[Latency:" in stdout
        if translation:
            assert translation in stdout
    exported = exporter.file_queue.get_nowait()
    assert task.transcript in exported
    if translation:
        assert translation in exported
    shared = exporter.subtitle_share_queue.get_nowait()
    assert shared["data"]["translated"] == translation
