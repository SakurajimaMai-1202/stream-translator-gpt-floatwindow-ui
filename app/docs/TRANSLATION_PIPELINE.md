# Translation Pipeline

The live pipeline keeps original and translated subtitles paired:

```text
audio -> VAD -> ASR -> overlap deduplication -> subtitle assembler
      -> prompt strategy -> provider -> ordered scheduler -> paired exporter
```

## Responsibilities

- `translation_policy.py`: request/result models, model capabilities, prompt strategies, output parsing.
- `llm_translator.py`: OpenAI, OpenAI-compatible and Gemini providers plus ordered scheduling.
- `subtitle_segmenter.py`: adjacent ASR overlap removal and bounded sentence assembly.
- `result_exporter.py`: ordered paired output and latency metadata.

Provider selection is derived from the configured translation backend. API keys are credentials only and must not select a provider.

## Model families

- `hy_mt2`: no system prompt, plain-text output, one concurrent request.
- `generic_chat`: system plus user messages, plain-text output, one concurrent request.
- `structured_api`: structured output when supported, two concurrent requests.
- `auto`: detects known Hy-MT2 names, otherwise uses provider capabilities.

Users can override auto detection because local OpenAI-compatible servers may expose generic model IDs such as `localllm`.

## Ordering

Translation requests may finish out of order. `ParallelTranslator` retains input order and only commits the leading completed or timed-out task. A failed request is retried at most once. Enabling translation history forces concurrency to one.

## Latency fields

Each subtitle task tracks:

- `asr_latency_ms`
- `translation_queue_latency_ms`
- `llm_latency_ms`
- `total_latency_ms`
- prompt and completion token counts when provided by the API
