import json
import queue
import sys
from types import SimpleNamespace

import pytest

from stream_translator_gpt import request_log
from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import LLMClient, ParallelTranslator, SerialTranslator


def make_client():
    return LLMClient("GPT", "custom", "Translate", 0, None, False,
                     provider="openai_compatible", api_key="test", output_format="text")


@pytest.mark.parametrize("retry,first_seconds,retry_seconds", [
    (False, 0.3, 0), (True, 6.2, 0.3), (True, 0.3, 6.2),
])
def test_parallel_attempt_timing_and_durable_log(
        monkeypatch, tmp_path, retry, first_seconds, retry_seconds):
    monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(tmp_path))
    clock = [10.0]
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.perf_counter", lambda: clock[0])
    client = make_client()
    task = TranslationTask([], (0, 1))
    task.transcript = "來源" * 400
    task.translation_queued_at = 9.0

    def translate(client, task):
        rejected = retry and task._translation_attempts == 1
        clock[0] += first_seconds if task._translation_attempts == 1 else retry_seconds
        task._attempt_raw_output = "拒絕" * 400 if rejected else "通過"
        task.translation = "" if rejected else "通過"
        client._validate_hy_mt2_output(task, task._attempt_raw_output)
        if rejected:
            task.translation_prompt_tokens = 42
            task._attempt_finish_reason = "stop"

    client.provider_adapter = SimpleNamespace(translate=translate)
    translator = ParallelTranslator(client, timeout=0, retry_if_translation_fails=retry)
    translator.processing_queue.append(task)
    translator._trigger(task)
    translator._scheduler_events.get(timeout=2)
    if retry:
        assert translator._get_results() == []
        translator._retrigger_failed_tasks()
        translator._scheduler_events.get(timeout=2)
    assert translator._get_results() == [task]
    assert task.translation_queue_latency_ms == pytest.approx(1000)
    assert task.latency_trace.translation_started_at == 10
    assert task.llm_latency_ms == pytest.approx(6500 if retry else 300)
    assert task.translation_result.generation_latency_ms == task.llm_latency_ms
    assert task.translation_retry_count == int(retry)
    assert task.translation_retry_ms == (pytest.approx(retry_seconds * 1000) if retry else None)
    from stream_translator_gpt.result_exporter import _format_latency_log
    assert (f"Retry {retry_seconds * 1000:.0f}ms" in _format_latency_log(task)) == retry
    records = [json.loads(line) for line in (tmp_path / "translation_requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(records) == (2 if retry else 1)
    assert "source" not in records[-1] and "raw_output" not in records[-1]
    assert records[-1]["prompt_tokens"] is None
    assert records[-1]["finish_reason"] is None
    if retry:
        assert records[0]["validation"] == ["empty_output"]
        assert records[-1]["validation"] == []
        assert len(records[0]["source"]) == len(records[0]["raw_output"]) == 300
        assert records[0]["attempt_ms"] == pytest.approx(first_seconds * 1000)
        assert records[0]["prompt_tokens"] == 42


@pytest.mark.parametrize("directory", [None, ""])
def test_disabled_log_creates_no_files(monkeypatch, tmp_path, directory):
    monkeypatch.chdir(tmp_path)
    if directory is None:
        monkeypatch.delenv("STREAM_TRANSLATOR_LOG_DIR", raising=False)
    else:
        monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", directory)
    request_log.log_attempt(None, None, 3000)
    assert list(tmp_path.iterdir()) == []


def test_logging_failure_cannot_break_translation(monkeypatch, tmp_path):
    monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(tmp_path))
    def fail(*args, **kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(request_log._logger, "info", fail)
    client = make_client()
    client.provider_adapter = SimpleNamespace(translate=lambda client, task: setattr(task, "translation", "成功"))
    task = TranslationTask([], (0, 1))
    client.translate(task)
    assert task.translation == "成功"
    assert not task.translation_failed
    monkeypatch.setattr(request_log, "log_attempt", fail)
    client.translate(task)
    assert not task.translation_failed


def test_gpu_missing_cloud_and_rate_limit(monkeypatch):
    calls = []
    monkeypatch.setattr(request_log, "_last_snapshot_at", None)
    monkeypatch.setattr(request_log.shutil, "which", lambda name: None)
    monkeypatch.setattr(request_log.threading, "Thread", lambda **kw: calls.append(kw))
    request_log._schedule_snapshot("http://127.0.0.1:8080", 1, 3000)
    assert calls == []
    inspected = []
    monkeypatch.setattr(request_log.shutil, "which", lambda name: inspected.append(name))
    request_log._schedule_snapshot("https://api.example.com", 1, 3000)
    assert inspected == []
    assert calls == []
    monkeypatch.setattr(request_log.shutil, "which", lambda name: "nvidia-smi")
    class Thread:
        def __init__(self, **kwargs):
            assert kwargs["daemon"]
        def start(self):
            calls.append("started")
    monkeypatch.setattr(request_log.threading, "Thread", Thread)
    now = [10.0]
    monkeypatch.setattr(request_log.time, "monotonic", lambda: now[0])
    request_log._schedule_snapshot("http://localhost:8080", 1, 3000)
    now[0] = 14.9
    request_log._schedule_snapshot("http://[::1]:8080", 2, 3000)
    assert calls == ["started"]
    now[0] = 15
    request_log._schedule_snapshot("http://[::1]:8080", 3, 3000)
    assert calls == ["started", "started"]


def test_gpu_snapshot_command_and_record(monkeypatch):
    records = []
    def run(command, **kwargs):
        assert command == ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total",
                           "--format=csv,noheader,nounits"]
        assert kwargs["timeout"] == 3
        assert kwargs["capture_output"] and kwargs["text"]
        assert "shell" not in kwargs
        return SimpleNamespace(returncode=0, stdout="75, 2048, 8192\n")
    monkeypatch.setattr(request_log.subprocess, "run", run)
    monkeypatch.setattr(request_log, "_write", records.append)
    request_log._gpu_snapshot("nvidia-smi", 7, 3000)
    assert records[0]["type"] == "gpu_snapshot"
    assert records[0]["util_pct"] == 75
    assert records[0]["mem_used_mb"] == 2048
    assert records[0]["mem_total_mb"] == 8192


def test_timeout_counts_from_first_attempt(monkeypatch):
    task = TranslationTask([], (0, 1))
    task._llm_first_started_at = 10
    task._llm_latency_started_at = 16
    task._llm_retry_started_at = 16
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.perf_counter", lambda: 17)
    ParallelTranslator(None, 0, True)._mark_timeout_latency(task)
    assert task.llm_latency_ms == 7000
    assert task.translation_retry_ms == 1000


def test_serial_timeout_during_retry_counts_from_first_attempt(monkeypatch):
    task = TranslationTask([], (0, 1))
    translator = SerialTranslator(None, 1, True)
    input_queue = queue.SimpleQueue()
    output_queue = queue.SimpleQueue()
    input_queue.put(task)
    input_queue.put(None)

    def trigger(current):
        current._translation_attempts = 2
        current._llm_first_started_at = 10
        current._llm_latency_started_at = 16
        current._llm_retry_started_at = 16
        current.llm_latency_ms = None

    monkeypatch.setattr(translator, "_trigger", trigger)
    monkeypatch.setattr("stream_translator_gpt.llm_translator._is_task_timeout", lambda *args: True)
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.perf_counter", lambda: 17)
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.sleep", lambda seconds: None)
    translator.loop(input_queue, output_queue)
    assert output_queue.get_nowait() is task
    assert task.llm_latency_ms == 7000
    assert task.translation_retry_ms == 1000
    assert task._translation_expired
    assert output_queue.get_nowait() is None


def test_retry_fields_are_set_while_second_attempt_is_in_flight(monkeypatch):
    client = make_client()
    task = TranslationTask([], (0, 1))
    task._llm_first_started_at = 10
    task._translation_attempts = 2
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.perf_counter", lambda: 16)
    observed = []

    def translate(client, current):
        observed.append((current.translation_retry_count, current.translation_retry_ms,
                         current._llm_retry_started_at))
        assert current.latency_trace.translation_finished_at is None
        current.translation = "translated"

    client.provider_adapter = SimpleNamespace(translate=translate)
    client.translate(task)
    assert observed == [(1, None, 16)]
    assert task.translation_retry_ms == 0


def test_empty_output_logs_validation_error(monkeypatch, tmp_path):
    monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(tmp_path))
    client = make_client()

    def translate(client, task):
        task.translation = ""
        client._validate_hy_mt2_output(task, "")

    client.provider_adapter = SimpleNamespace(translate=translate)
    task = TranslationTask([], (0, 1))
    client.translate(task)
    records = [json.loads(line) for line in
               (tmp_path / "translation_requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert task._attempt_error == "ValueError"
    assert records[0]["error"] == "empty_output"


def test_gemini_text_failure_preserves_response_metadata(monkeypatch):
    class Response:
        candidates = [SimpleNamespace(finish_reason=SimpleNamespace(name="SAFETY"))]
        usage_metadata = SimpleNamespace(prompt_token_count=42, candidates_token_count=7)

        @property
        def text(self):
            raise ValueError("blocked response")

    fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw,
                                 SafetySetting=lambda **kw: kw,
                                 ThinkingConfig=lambda **kw: kw)
    fake_genai = SimpleNamespace(
        types=fake_types,
        Client=lambda **kw: SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kw: Response())))
    monkeypatch.setitem(sys.modules, "google", SimpleNamespace(genai=fake_genai))
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr("stream_translator_gpt.llm_translator.ApiKeyPool.use_google_api", lambda: None)
    client = make_client()
    monkeypatch.setattr(client, "_prepare_prompt", lambda task: SimpleNamespace(
        user_content="source", temperature=0, top_p=1, output_format="text",
        system_instruction="Translate"))
    client.provider_adapter = SimpleNamespace(translate=lambda client, task: client._translate_by_gemini(task))
    task = TranslationTask([], (0, 1))
    client.translate(task)
    assert task.translation_failed
    assert task.translation_error == "blocked response"
    assert task._attempt_finish_reason == "SAFETY"
    assert task.translation_prompt_tokens == 42
    assert task.translation_completion_tokens == 7


@pytest.mark.parametrize("validation,raw_output,keep_raw", [
    (("prompt_leakage",), "echoed prompt", False),
    (("unexpected_multiline_output",), "<think>private reasoning", False),
    (("unexpected_multiline_output",), "private reasoning</think>", False),
    (("unexpected_multiline_output",), "first line\nsecond line", True),
] + [(("unexpected_multiline_output",), "x" * 301 + marker, False)
     for marker in request_log.PROMPT_LEAKAGE_MARKERS])
def test_attempt_log_suppresses_prompt_echoes(
        monkeypatch, tmp_path, validation, raw_output, keep_raw):
    monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(tmp_path))
    task = TranslationTask([], (0, 1))
    task.transcript = "source"
    task._attempt_validation = validation
    task._attempt_finish_reason = None
    task._attempt_raw_output = raw_output
    request_log.log_attempt(make_client(), task, 300)
    record, = [json.loads(line) for line in
               (tmp_path / "translation_requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert record["validation"] == list(validation)
    assert record["source"] == "source"
    assert ("raw_output" in record) == keep_raw
    if keep_raw:
        assert record["raw_output"] == raw_output


def test_retry_timer_starts_once_and_finishes_on_failure(monkeypatch):
    client = make_client()
    task = TranslationTask([], (0, 1))
    task._llm_first_started_at = 10
    task._translation_attempts = 2
    clock = [10.3]
    monkeypatch.setattr("stream_translator_gpt.llm_translator.time.perf_counter", lambda: clock[0])

    def translate(client, current):
        clock[0] += 6.2
        raise RuntimeError("retry failed")

    client.provider_adapter = SimpleNamespace(translate=translate)
    client.translate(task)
    assert task.translation_retry_ms == pytest.approx(6200)
    task._translation_attempts = 3
    client.translate(task)
    assert task._llm_retry_started_at == 10.3
    assert task.translation_retry_count == 2
    assert task.translation_retry_ms == pytest.approx(12400)


def test_gpt_attempt_raw_output_matches_stripped_validation_text(monkeypatch):
    client = make_client()
    client.model_family = "index_translate"
    completion = SimpleNamespace(choices=[SimpleNamespace(
        message=SimpleNamespace(content="<think>echoed prompt</think>first line\nsecond line"),
        finish_reason="stop")])
    client._openai_clients["test"] = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=lambda **kwargs: completion)))
    monkeypatch.setattr(client, "_prepare_prompt", lambda task: SimpleNamespace(
        user_content="source", system_instruction="Translate", temperature=0, top_p=1,
        output_format="text"))
    seen = []
    monkeypatch.setattr(client, "_validate_hy_mt2_output",
                        lambda task, text: seen.append(text))
    task = TranslationTask([], (0, 1))
    task.transcript = "source"
    client.translate(task)
    assert seen == ["first line\nsecond line"]
    assert task._attempt_raw_output == seen[0]
