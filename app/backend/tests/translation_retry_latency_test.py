from backend.core.translator import _extract_latency_metrics, _parse_structured_subtitle_event


def test_retry_and_existing_latency_labels():
    line, metrics = _extract_latency_metrics("subtitle [Latency: ASR 1ms LLM 6500ms Queue 2ms Retry 123ms Total 7000ms]")
    assert line == "subtitle"
    assert metrics == dict(asr_latency_ms=1, llm_latency_ms=6500,
                           translation_queue_latency_ms=2, translation_retry_ms=123,
                           total_latency_ms=7000)


def test_structured_retry_fields_pass_through():
    data = _parse_structured_subtitle_event('__ST_SUBTITLE_EVENT__{"translation_retry_ms":123,"translation_retry_count":1}')
    assert data["translation_retry_ms"] == 123
    assert data["translation_retry_count"] == 1
