import json
import queue
import threading
import time

import numpy as np

from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import ParallelTranslator
from stream_translator_gpt.result_exporter import ResultExporter
from stream_translator_gpt.subtitle_segmenter import SubtitleSegmenter, remove_text_overlap
from stream_translator_gpt.translation_policy import (
    TranslationRequest,
    create_prompt_strategy,
    get_capabilities,
    parse_translation_output,
    resolve_model_family,
    resolve_output_format,
)


def test_hymt2_policy_uses_single_user_prompt_and_plain_text():
    family = resolve_model_family("hy_mt2", "localllm", "openai_compatible")
    capabilities = get_capabilities(family)
    output_format = resolve_output_format("json", capabilities)
    strategy = create_prompt_strategy(
        family,
        "將以下日文翻譯為繁體中文，只輸出翻譯結果，不要額外解釋",
        output_format,
    )

    prepared = strategy.prepare(TranslationRequest(
        segment_id=7,
        source_text="今日はマリーと遊びます",
        previous_original="昨日は雨でした",
        glossary={"マリー": "瑪麗", "未出現": "ignored"},
    ))

    assert prepared.system_instruction is None
    assert prepared.output_format == "text"
    assert "マリー 翻译成 瑪麗" in prepared.user_content
    assert "昨日は雨でした" in prepared.user_content
    assert "繁體中文" in prepared.user_content
    assert prepared.temperature == 0.7
    assert prepared.top_p == 0.6
    assert prepared.top_k == 20
    assert prepared.repetition_penalty == 1.05


def test_model_family_auto_detection_and_output_parsing():
    assert resolve_model_family("auto", "Tencent-Hunyuan/Hy-MT2-7B", "openai_compatible") == "hy_mt2"
    assert resolve_model_family("auto", "gemma", "openai_compatible") == "generic_chat"
    assert resolve_model_family("auto", "gpt-5-mini", "openai") == "structured_api"
    assert parse_translation_output('```json\n{"translation":"測試"}\n```', "json") == "測試"
    assert parse_translation_output("純文字翻譯", "text") == "純文字翻譯"


class _DelayedClient:
    def translate(self, task):
        time.sleep({1: 0.08, 2: 0.01}.get(task.segment_id, 0.01))
        task.translation = f"translated-{task.segment_id}"
        task.llm_latency_ms = 1.0
        task._translation_inflight = False


def _task(segment_id: int) -> TranslationTask:
    task = TranslationTask(np.zeros(512, dtype=np.float32), (0.0, 1.0))
    task.segment_id = segment_id
    task.transcript = f"source-{segment_id}"
    return task


def test_parallel_translator_commits_completed_tasks_in_segment_order():
    translator = ParallelTranslator(
        llm_client=_DelayedClient(),
        timeout=2,
        retry_if_translation_fails=False,
        max_concurrency=2,
    )
    input_queue = queue.SimpleQueue()
    output_queue = queue.SimpleQueue()
    for segment_id in (1, 2):
        input_queue.put(_task(segment_id))
    input_queue.put(None)

    worker = threading.Thread(target=translator.loop, args=(input_queue, output_queue))
    worker.start()
    worker.join(timeout=3)

    assert not worker.is_alive()
    assert output_queue.get().segment_id == 1
    assert output_queue.get().segment_id == 2
    assert output_queue.get() is None


def test_paired_exporter_skips_original_only_task():
    received = []
    exporter = ResultExporter(
        cqhttp_url=None,
        cqhttp_token=None,
        discord_webhook_url=None,
        telegram_token=None,
        telegram_chat_id=None,
        output_file_path=None,
        proxy=None,
        output_whisper_result=True,
        output_timestamps=False,
        gui_callback=received.append,
        require_translation=True,
    )
    failed = _task(1)
    successful = _task(2)
    successful.translation = "譯文"
    input_queue = queue.SimpleQueue()
    input_queue.put(failed)
    input_queue.put(successful)
    input_queue.put(None)

    exporter.loop(input_queue)

    assert [task.segment_id for task in received] == [2]


def test_subtitle_event_includes_latency_breakdown():
    exporter = ResultExporter(
        cqhttp_url=None,
        cqhttp_token=None,
        discord_webhook_url=None,
        telegram_token=None,
        telegram_chat_id=None,
        output_file_path=None,
        proxy=None,
        output_whisper_result=True,
        output_timestamps=False,
    )
    exporter.subtitle_share_queue = queue.SimpleQueue()
    task = _task(3)
    task.translation = "譯文"
    task.asr_latency_ms = 420.25
    task.translation_queue_latency_ms = 35.4
    task.llm_latency_ms = 1210.8
    task.total_latency_ms = 2080.1
    input_queue = queue.SimpleQueue()
    input_queue.put(task)
    input_queue.put(None)

    exporter.loop(input_queue)

    event = exporter.subtitle_share_queue.get()
    assert event["event"] == "subtitle"
    assert event["data"]["asr_latency_ms"] == 420.2
    assert event["data"]["translation_queue_latency_ms"] == 35.4
    assert event["data"]["llm_latency_ms"] == 1210.8
    assert event["data"]["total_latency_ms"] == 2080.1


def test_machine_readable_subtitle_event_includes_latency(capsys):
    exporter = ResultExporter(
        cqhttp_url=None,
        cqhttp_token=None,
        discord_webhook_url=None,
        telegram_token=None,
        telegram_chat_id=None,
        output_file_path=None,
        proxy=None,
        output_whisper_result=True,
        output_timestamps=False,
        emit_json_events=True,
    )
    task = _task(4)
    task.translation = "譯文"
    task.total_latency_ms = 987.6
    input_queue = queue.SimpleQueue()
    input_queue.put(task)
    input_queue.put(None)

    exporter.loop(input_queue)

    marker_line = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("__ST_SUBTITLE_EVENT__")
    )
    payload = json.loads(marker_line.removeprefix("__ST_SUBTITLE_EVENT__"))
    assert payload["segment_id"] == 4
    assert payload["translated"] == "譯文"
    assert payload["total_latency_ms"] == 987.6


def test_overlap_deduplication_is_conservative_for_cjk_and_latin():
    assert remove_text_overlap(
        "今日は新しいゲームを",
        "新しいゲームを始めます",
    ) == "始めます"
    assert remove_text_overlap(
        "We are testing the new game",
        "the new game today",
    ) == "today"
    assert remove_text_overlap("今日は雨", "今日は晴れ") == "今日は晴れ"


def test_subtitle_assembler_merges_adjacent_incomplete_segments():
    segmenter = SubtitleSegmenter(
        deduplicate_overlap=False,
        assembler_enabled=True,
        assembler_wait_ms=100,
        assembler_max_duration=6.0,
        assembler_gap_threshold=0.8,
    )
    first = _task(1)
    first.transcript = "もし明日雨なら"
    first.raw_transcript = first.transcript
    first.time_range = (0.0, 2.0)
    second = _task(2)
    second.transcript = "室内に変更します。"
    second.raw_transcript = second.transcript
    second.time_range = (2.1, 4.0)
    input_queue = queue.SimpleQueue()
    output_queue = queue.SimpleQueue()
    input_queue.put(first)
    input_queue.put(second)
    input_queue.put(None)

    segmenter.loop(input_queue, output_queue)
    merged = output_queue.get()

    assert merged.segment_id == 1
    assert merged.transcript == "もし明日雨なら室内に変更します。"
    assert merged.time_range == (0.0, 4.0)
    assert output_queue.get() is None
