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

## Optional HY-MT2 subtitle optimizer

In Settings → Translation, **套用日文直播推薦設定** enables the HY-MT2
strategy, Traditional Chinese target, the existing terminology list, three
Japanese context sentences, and Taiwan subtitle style. It keeps the currently
selected translation model and its provider. The panel displays the effective
model and glossary count; advanced settings stay available under
**後端與進階參數**. Configuration saves automatically. Start a new translation
task to load it.

**測試目前模型** saves the translation settings, then makes one short inference
request to the selected OpenAI-compatible backend. It confirms connectivity,
model ID, and response shape. The sample response does not score translation
quality or exercise the full live ASR pipeline.

`translation.hy_mt2_optimizer_enabled` defaults to `false`. When enabled for the
`hy_mt2` model family, the prompt uses the existing enabled terminology glossary,
its optional `glossary_list[].aliases`, recent Japanese source subtitles, the
Taiwan subtitle style, and optional `hy_mt2_preferences`. No other model family
uses this prompt. Enable the built-in glossary separately in Terminology; the
optional JSON folder can supply terms even when that list is empty.

`hy_mt2_context_window` is clamped to 0–5 (default 3),
`hy_mt2_max_context_chars` to 0–4000 (default 1000), and `hy_mt2_max_terms`
to 0–30 (default 10). Context forces one translation request at a time so
the next prompt can use completed source subtitles. `hy_mt2_debug` writes the
source, full prompt, and output to logs; leave it off when subtitle content
should not be logged.

`hy_mt2_provider` can be `existing`, `lm_studio`, or `llama_cpp`. The two local
choices use the same OpenAI-compatible chat completion transport; set each
server URL and exact model ID in its own fields. Changing the provider requires
restarting the translation task, not the desktop app. A missing local model ID
fails at configuration time instead of falling back to another provider.
`hy_mt2_glossary_folder` optionally loads JSON files containing either
`{"原文": "譯名"}` or records such as
`{"星街すいせい": {"target": "Suisei", "aliases": ["すいちゃん"]}}`.
Relative paths resolve beside the saved configuration file. Files are read when
the translation task starts; restart the task after editing them.
`hy_mt2_style_text` is editable in the settings page.

## Ordering

Translation requests may finish out of order. `ParallelTranslator` retains input order and only commits the leading completed or timed-out task. A failed request is retried at most once. Enabling translation history forces concurrency to one.

## Latency fields

Each subtitle task tracks:

- `asr_latency_ms`
- `translation_queue_latency_ms`
- `llm_latency_ms`
- `total_latency_ms`
- prompt and completion token counts when provided by the API
