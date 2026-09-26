import os
import queue
import threading
import time

from .audio_getter import StreamAudioGetter, LocalFileAudioGetter, DeviceAudioGetter
from .audio_slicer import AudioSlicer
from .common import ClientPool, INFO, is_url, PipelineWorkers
from .result_exporter import ResultExporter
from .subtitle_segmenter import SubtitleSegmenter


class PipelineController:

    def __init__(self) -> None:
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self.audio_getter = None

    def set_audio_getter(self, audio_getter) -> None:
        with self._lock:
            self.audio_getter = audio_getter
            if self.stop_event.is_set() and hasattr(audio_getter, "stop"):
                audio_getter.stop()

    def request_stop(self) -> None:
        self.stop_event.set()
        with self._lock:
            audio_getter = self.audio_getter
        if audio_getter is not None and hasattr(audio_getter, "stop"):
            audio_getter.stop()


def create_audio_getter(url: str, options: dict):
    if options.get("loopback") or url.lower() == "loopback":
        return DeviceAudioGetter(
            device_index=options.get("device_index"),
            recording_interval=options.get("device_recording_interval"),
            use_loopback=True,
        )
    if url.lower() == "device":
        return DeviceAudioGetter(
            device_index=options.get("device_index"),
            recording_interval=options.get("device_recording_interval"),
            use_loopback=False,
        )
    if is_url(url):
        return StreamAudioGetter(
            url=url,
            format=options.get("format"),
            cookies=options.get("cookies"),
            proxy=options.get("input_proxy"),
        )
    return LocalFileAudioGetter(file_path=url)


def create_slicer(options: dict):
    return AudioSlicer(
        min_audio_length=options.get("min_audio_length"),
        max_audio_length=options.get("max_audio_length"),
        target_audio_length=options.get("target_audio_length"),
        continuous_no_speech_threshold=options.get("continuous_no_speech_threshold"),
        dynamic_no_speech_threshold=not bool(options.get("disable_dynamic_no_speech_threshold")),
        prefix_retention_length=options.get("prefix_retention_length"),
        vad_threshold=options.get("vad_threshold"),
        dynamic_vad_threshold=not bool(options.get("disable_dynamic_vad_threshold")),
        vad_backend=options.get("vad_backend"),
        firered_vad_model_path=options.get("firered_vad_model_path"),
        disable_vad=bool(options.get("disable_vad")),
        vad_every_n_frames=options.get("vad_every_n_frames", 1),
        slicing_mode=options.get("slicing_mode", "omnivad_native"),
        omnivad_smooth_window_size=options.get("omnivad_smooth_window_size", 5),
        omnivad_pad_start_frame=options.get("omnivad_pad_start_frame", 5),
        omnivad_min_speech_frame=options.get("omnivad_min_speech_frame", 8),
        omnivad_max_speech_frame=options.get("omnivad_max_speech_frame", 2000),
        omnivad_min_silence_frame=options.get("omnivad_min_silence_frame", 20),
        omnivad_threshold=options.get("omnivad_threshold", 0.35),
    )


def create_translator(options: dict):
    if not options.get("translation_prompt"):
        return None
    import json as _json
    glossary = {}
    translation_glossary = options.get("translation_glossary")
    if translation_glossary:
        try:
            glossary = _json.loads(translation_glossary)
            if not isinstance(glossary, dict):
                glossary = {}
        except (ValueError, TypeError):
            pass

    from .llm_translator import LLMClient, ParallelTranslator
    from .translation_policy import get_capabilities, resolve_model_family
    provider = options.get("translation_provider") or (
        "gemini" if options.get("google_api_key") else (
            "openai_compatible" if options.get("openai_base_url") else "openai"
        )
    )
    model = options.get("gemini_model") if provider == "gemini" else options.get("gpt_model")
    model_family = resolve_model_family(
        options.get("translation_model_family"),
        model,
        provider,
    )
    capabilities = get_capabilities(model_family)
    requested_concurrency = int(options.get("translation_max_concurrency") or 0)
    max_concurrency = requested_concurrency or capabilities.default_max_concurrency
    if options.get("translation_history_size", 0):
        max_concurrency = 1

    if provider == "gemini":
        llm_client = LLMClient(
            llm_type=LLMClient.LLM_TYPE.GEMINI,
            model=options.get("gemini_model"),
            prompt=options.get("translation_prompt"),
            history_size=options.get("translation_history_size", 0),
            proxy=options.get("processing_proxy"),
            use_json_result=options.get("use_json_result"),
            gemini_base_url=options.get("gemini_base_url"),
            glossary=glossary,
            model_family=model_family,
            output_format=options.get("translation_output_format", "auto"),
            max_output_tokens=options.get("translation_max_output_tokens", 128),
            provider=provider,
        )
    else:
        llm_client = LLMClient(
            llm_type=LLMClient.LLM_TYPE.GPT,
            model=options.get("gpt_model"),
            prompt=options.get("translation_prompt"),
            history_size=options.get("translation_history_size", 0),
            proxy=options.get("processing_proxy"),
            use_json_result=options.get("use_json_result"),
            glossary=glossary,
            model_family=model_family,
            output_format=options.get("translation_output_format", "auto"),
            max_output_tokens=options.get("translation_max_output_tokens", 128),
            provider=provider,
        )

    return ParallelTranslator(
        llm_client=llm_client,
        timeout=options.get("translation_timeout", 10),
        retry_if_translation_fails=options.get("retry_if_translation_fails", True),
        max_concurrency=max_concurrency,
    )


def create_exporter(options: dict, subtitle_share_push_url: str | None, subtitle_share_token: str | None):
    return ResultExporter(
        cqhttp_url=options.get("cqhttp_url"),
        cqhttp_token=options.get("cqhttp_token"),
        discord_webhook_url=options.get("discord_webhook_url"),
        telegram_token=options.get("telegram_token"),
        telegram_chat_id=options.get("telegram_chat_id"),
        output_file_path=options.get("output_file_path"),
        proxy=options.get("output_proxy"),
        output_whisper_result=not bool(options.get("hide_transcribe_result")),
        output_timestamps=bool(options.get("output_timestamps")),
        show_latency_log=bool(options.get("show_latency_log")),
        emit_json_events=bool(options.get("emit_json_events")),
        require_translation=bool(
            options.get("translation_prompt")
            and not options.get("disable_paired_subtitle_mode", False)
        ),
        subtitle_share_push_url=subtitle_share_push_url,
        subtitle_share_token=subtitle_share_token,
    )


def create_subtitle_segmenter(options: dict):
    return SubtitleSegmenter(
        deduplicate_overlap=not options.get("disable_asr_overlap_deduplication", False),
        assembler_enabled=not options.get("disable_subtitle_assembler", False),
        assembler_wait_ms=options.get("subtitle_assembler_wait_ms", 400),
        assembler_max_duration=options.get("subtitle_assembler_max_duration", 6.0),
        assembler_gap_threshold=options.get("subtitle_assembler_gap_threshold", 0.8),
        print_result=not bool(options.get("hide_transcribe_result")),
        output_timestamps=bool(options.get("output_timestamps")),
    )


def run_inprocess_pipeline(url: str,
                           options: dict,
                           transcriber,
                           controller: PipelineController | None = None,
                           subtitle_share_push_url: str | None = None,
                           subtitle_share_token: str | None = None) -> int:
    if options.get("proxy"):
        proxy = options.get("proxy")
        os.environ["http_proxy"] = proxy
        os.environ["https_proxy"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
    if options.get("openai_base_url"):
        os.environ["OPENAI_BASE_URL"] = options.get("openai_base_url")

    ClientPool.init(openai_api_key=options.get("openai_api_key"),
                    google_api_key=options.get("google_api_key"),
                    proxy=options.get("processing_proxy"),
                    google_base_url=options.get("google_base_url"))

    getter_to_slicer_queue = queue.SimpleQueue()
    slicer_to_transcriber_queue = queue.SimpleQueue()
    transcriber_to_segmenter_queue = queue.SimpleQueue()
    segmenter_to_translator_queue = queue.SimpleQueue()
    translator_to_exporter_queue = queue.SimpleQueue() if options.get("translation_prompt") else segmenter_to_translator_queue

    audio_getter = create_audio_getter(url, options)
    if controller is not None:
        controller.set_audio_getter(audio_getter)

    slicer = create_slicer(options)
    translator = create_translator(options)
    segmenter = create_subtitle_segmenter(options)
    # The segmenter decides which ASR results actually enter translation.
    # Printing earlier leaves untranslated rows behind for discarded overlaps.
    transcriber.print_result = False
    exporter = create_exporter(options, subtitle_share_push_url, subtitle_share_token)

    workers = PipelineWorkers()
    print(f"{INFO}Initialization complete, starting up...")
    workers.start(audio_getter.loop, output_queue=getter_to_slicer_queue)
    workers.start(slicer.loop, input_queue=getter_to_slicer_queue, output_queue=slicer_to_transcriber_queue)
    workers.start(transcriber.loop,
                        input_queue=slicer_to_transcriber_queue,
                        output_queue=transcriber_to_segmenter_queue)
    workers.start(segmenter.loop,
                        input_queue=transcriber_to_segmenter_queue,
                        output_queue=segmenter_to_translator_queue)
    if translator:
        workers.start(translator.loop,
                            input_queue=segmenter_to_translator_queue,
                            output_queue=translator_to_exporter_queue)
    exporter_thread = workers.start(exporter.loop, input_queue=translator_to_exporter_queue)

    try:
        while exporter_thread.is_alive():
            if controller is not None and controller.stop_event.is_set():
                if hasattr(audio_getter, "stop"):
                    audio_getter.stop()
            workers.raise_if_failed()
            time.sleep(0.2)
        workers.raise_if_failed()
    finally:
        if hasattr(audio_getter, "stop"):
            audio_getter.stop()
        for pending in (getter_to_slicer_queue, slicer_to_transcriber_queue,
                        transcriber_to_segmenter_queue, segmenter_to_translator_queue,
                        translator_to_exporter_queue):
            pending.put(None)
    print(f"{INFO}All processing completed, program exits.")
    return 0
