import argparse
import os
import queue
import signal
import sys
import time
import subprocess
import shutil
import platform
import threading
from concurrent.futures import ThreadPoolExecutor

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "stream_translator_gpt"

from .common import ApiKeyPool, start_daemon_thread, is_url, WARNING, ERROR, INFO
from .audio_getter import (
    StreamAudioGetter,
    LocalFileAudioGetter,
    DeviceAudioGetter,
    _append_site_specific_ytdlp_args,
    _resolve_cookie_file,
)
from .audio_slicer import AudioSlicer
from .audio_transcriber import OpenaiWhisper, FasterWhisper, SimulStreaming, RemoteOpenaiTranscriber, Qwen3ASRTranscriber, HFTranscriber, NemoASRTranscriber
from .llm_translator import LLMClient, ParallelTranslator, SerialTranslator
from .result_exporter import ResultExporter
from .subtitle_sharing import DEFAULT_PUBLIC_HOST, DEFAULT_PUBLIC_PORT, SubtitleShareServer, create_task_id
from .asr_preload import PreloadedTranscriberManager, build_asr_config
from .pipeline_runner import PipelineController, run_inprocess_pipeline
from .runtime_accelerator import resolve_qwen3_device_map
from . import __version__


def main(url, **kwargs):
    # Extract args
    loopback = kwargs.get('loopback', False)
    device_index = kwargs.get('device_index')
    device_recording_interval = kwargs.get('device_recording_interval', 0.5)
    format = kwargs.get('format', 'ba/wa*')
    cookies = kwargs.get('cookies')
    input_proxy = kwargs.get('input_proxy')
    realtime_processing = kwargs.get('realtime_processing', False)
    min_audio_length = kwargs.get('min_audio_length', 0.5)
    max_audio_length = kwargs.get('max_audio_length', 30.0)
    target_audio_length = kwargs.get('target_audio_length', 5.0)
    continuous_no_speech_threshold = kwargs.get('continuous_no_speech_threshold', 1.0)
    disable_dynamic_no_speech_threshold = kwargs.get('disable_dynamic_no_speech_threshold', False)
    prefix_retention_length = kwargs.get('prefix_retention_length', 0.5)
    vad_threshold = kwargs.get('vad_threshold', 0.35)
    disable_dynamic_vad_threshold = kwargs.get('disable_dynamic_vad_threshold', False)
    vad_every_n_frames = kwargs.get('vad_every_n_frames', 1)
    vad_backend = kwargs.get('vad_backend', 'silero')
    firered_vad_model_path = kwargs.get('firered_vad_model_path')

    whisper_filters = kwargs.get('whisper_filters', 'emoji_filter,repetition_filter')
    transcription_filters = kwargs.get('transcription_filters')
    if transcription_filters:
        whisper_filters = transcription_filters
    hide_transcribe_result = kwargs.get('hide_transcribe_result', False)
    output_timestamps = kwargs.get('output_timestamps', False)
    show_latency_log = kwargs.get('show_latency_log', False)
    disable_transcription_context = kwargs.get('disable_transcription_context', False)
    transcription_initial_prompt = kwargs.get('transcription_initial_prompt')
    asr_corrections_enabled = kwargs.get('asr_corrections_enabled', False)
    asr_correction_rules = kwargs.get('asr_correction_rules')
    asr_corrections_case_sensitive = kwargs.get('asr_corrections_case_sensitive', False)
    runtime_profile = kwargs.get('runtime_profile', 'cuda')
    runtime_device_policy = kwargs.get('runtime_device_policy', 'auto_discrete')
    runtime_allow_integrated_gpu = kwargs.get('runtime_allow_integrated_gpu', False)

    use_qwen3_asr = kwargs.get('use_qwen3_asr', False)
    qwen3_asr_model = kwargs.get('qwen3_asr_model')
    qwen3_asr_dtype = kwargs.get('qwen3_asr_dtype', 'bfloat16')
    qwen3_asr_device_map = kwargs.get('qwen3_asr_device_map', 'auto')
    qwen3_asr_max_new_tokens = kwargs.get('qwen3_asr_max_new_tokens', 128)
    qwen3_asr_quantization = kwargs.get('qwen3_asr_quantization', 'none')
    qwen3_asr_bnb_4bit_quant_type = kwargs.get('qwen3_asr_bnb_4bit_quant_type', 'nf4')
    qwen3_asr_bnb_4bit_use_double_quant = kwargs.get('qwen3_asr_bnb_4bit_use_double_quant', False)

    qwen3_context = kwargs.get('qwen3_context')
    qwen3_dtype = kwargs.get('qwen3_dtype', 'bfloat16')
    qwen3_load_in_4bit = kwargs.get('qwen3_load_in_4bit', False)
    qwen3_rms_threshold = kwargs.get('qwen3_rms_threshold', 0.005)

    use_hf_asr = kwargs.get('use_hf_asr', False)
    use_nemo_asr = kwargs.get('use_nemo_asr', False)
    nemo_asr_model = kwargs.get('nemo_asr_model')
    nemo_asr_device = kwargs.get('nemo_asr_device')
    nemo_asr_decoding = kwargs.get('nemo_asr_decoding')

    model = kwargs.get('model', 'turbo')
    language = kwargs.get('language')
    use_faster_whisper = kwargs.get('use_faster_whisper', False)
    use_simul_streaming = kwargs.get('use_simul_streaming', False)
    use_openai_transcription_api = kwargs.get('use_openai_transcription_api', False)
    openai_transcription_model = kwargs.get('openai_transcription_model', 'gpt-4o-mini-transcribe')
    processing_proxy = kwargs.get('processing_proxy')
    openai_api_key = kwargs.get('openai_api_key')
    google_api_key = kwargs.get('google_api_key')

    translation_prompt = kwargs.get('translation_prompt')
    gemini_model = kwargs.get('gemini_model', 'gemini-2.5-flash-lite')
    gpt_model = kwargs.get('gpt_model', 'gpt-5-nano')
    translation_history_size = kwargs.get('translation_history_size', 0)
    use_json_result = kwargs.get('use_json_result', False)
    gemini_base_url = kwargs.get('gemini_base_url')
    gpt_base_url = kwargs.get('gpt_base_url')
    openai_base_url = kwargs.get('openai_base_url')
    google_base_url = kwargs.get('google_base_url')
    if openai_base_url and not gpt_base_url:
        gpt_base_url = openai_base_url
    if google_base_url and not gemini_base_url:
        gemini_base_url = google_base_url

    translation_glossary = kwargs.get('translation_glossary')
    translation_timeout = kwargs.get('translation_timeout', 10)
    retry_if_translation_fails = kwargs.get('retry_if_translation_fails', False)

    output_file_path = kwargs.get('output_file_path')
    output_proxy = kwargs.get('output_proxy')
    cqhttp_url = kwargs.get('cqhttp_url')
    cqhttp_token = kwargs.get('cqhttp_token')
    discord_webhook_url = kwargs.get('discord_webhook_url')
    telegram_token = kwargs.get('telegram_token')
    telegram_chat_id = kwargs.get('telegram_chat_id')

    if gpt_base_url:
        os.environ['OPENAI_BASE_URL'] = gpt_base_url

    ApiKeyPool.init(openai_api_key=openai_api_key, google_api_key=google_api_key)

    # Init Subtitle Sharing Server if enabled
    managed_subtitle_share_server = None
    managed_subtitle_share_task_id = None
    subtitle_share_push_url = None
    subtitle_share_token = None
    if kwargs.get("enable_subtitle_sharing"):
        managed_subtitle_share_server = _start_subtitle_share_server(
            kwargs.get("subtitle_share_host", DEFAULT_PUBLIC_HOST),
            kwargs.get("subtitle_share_public_port", DEFAULT_PUBLIC_PORT)
        )
        managed_subtitle_share_task_id = create_task_id()
        managed_subtitle_share_server.begin_task(managed_subtitle_share_task_id, os.getpid())
        subtitle_share_push_url = f'http://127.0.0.1:{managed_subtitle_share_server.port}/api/translation/push/{managed_subtitle_share_task_id}'
        subtitle_share_token = managed_subtitle_share_server.push_token

    # Init queues
    getter_to_slicer_queue = queue.SimpleQueue()
    slicer_to_transcriber_queue = queue.SimpleQueue()
    transcriber_to_translator_queue = queue.SimpleQueue()
    translator_to_exporter_queue = queue.SimpleQueue() if translation_prompt else transcriber_to_translator_queue

    # Init workers
    with ThreadPoolExecutor() as executor:

        def init_audio_getter():
            # 自動模式
            if loopback or url.lower() == 'loopback':
                import sys
                if sys.platform == 'win32':
                    print(f'{INFO}自動捕獲模式：使用 WASAPI Loopback 捕獲系統預設播放設備音頻。')
                    return DeviceAudioGetter(
                        device_index=device_index,
                        recording_interval=device_recording_interval,
                        use_loopback=True,
                    )
                else:
                    print(f'{ERROR}WASAPI Loopback 僅支援 Windows 平台。')
                    print(f'{INFO}請提供 URL、檔案路徑或使用 "device" 參數。')
                    sys.exit(1)
            elif url.lower() == 'device':
                return DeviceAudioGetter(
                    device_index=device_index,
                    recording_interval=device_recording_interval,
                    use_loopback=False,
                )
            elif is_url(url):
                return StreamAudioGetter(
                    url=url,
                    format=format,
                    cookies=cookies,
                    proxy=input_proxy,
                    realtime_throttle=realtime_processing,
                )
            else:
                return LocalFileAudioGetter(file_path=url, realtime_throttle=realtime_processing)

        audio_getter_future = executor.submit(init_audio_getter)
        slicer_future = executor.submit(
            AudioSlicer,
            min_audio_length=min_audio_length,
            max_audio_length=max_audio_length,
            target_audio_length=target_audio_length,
            continuous_no_speech_threshold=continuous_no_speech_threshold,
            dynamic_no_speech_threshold=not disable_dynamic_no_speech_threshold,
            prefix_retention_length=prefix_retention_length,
            vad_threshold=vad_threshold,
            dynamic_vad_threshold=not disable_dynamic_vad_threshold,
            vad_every_n_frames=vad_every_n_frames,
            disable_vad=False,
            vad_backend=vad_backend,
            firered_vad_model_path=firered_vad_model_path,
        )

        def init_transcriber():
            common_args = {
                'whisper_filters': whisper_filters,
                'print_result': not hide_transcribe_result,
                'output_timestamps': output_timestamps,
                'disable_transcription_context': disable_transcription_context,
                'transcription_initial_prompt': transcription_initial_prompt,
                'asr_corrections_enabled': asr_corrections_enabled,
                'asr_correction_rules': asr_correction_rules,
                'asr_corrections_case_sensitive': asr_corrections_case_sensitive,
            }
            if use_qwen3_asr:
                import torch
                qwen_model = qwen3_asr_model or model
                qwen_dtype = qwen3_asr_dtype or qwen3_dtype
                qwen_quant = qwen3_asr_quantization or ('bnb_4bit' if qwen3_load_in_4bit else 'none')
                qwen_device_map = resolve_qwen3_device_map(
                    torch_module=torch,
                    requested_device_map=qwen3_asr_device_map,
                    runtime_profile=runtime_profile,
                    device_policy=runtime_device_policy,
                    allow_integrated_gpu=runtime_allow_integrated_gpu,
                )
                if qwen_device_map == 'cpu' and str(qwen_dtype).lower() in {'bfloat16', 'float16'}:
                    qwen_dtype = 'float32'
                    print(f'{INFO}Qwen3-ASR fell back to CPU; using float32 dtype for compatibility')
                print(f'{INFO}Qwen3-ASR device map resolved: {qwen_device_map} '
                      f'(profile={runtime_profile}, policy={runtime_device_policy})')
                return Qwen3ASRTranscriber(model=qwen_model, language=language,
                                          dtype=qwen_dtype, device_map=qwen_device_map,
                                          quantization=qwen_quant,
                                          rms_threshold=qwen3_rms_threshold, **common_args)
            elif use_hf_asr:
                return HFTranscriber(model=model, language=language, proxy=processing_proxy, **common_args)
            elif use_nemo_asr:
                return NemoASRTranscriber(**common_args)
            elif use_simul_streaming:
                return SimulStreaming(model=model,
                                      language=language,
                                      use_faster_whisper=use_faster_whisper,
                                      **common_args)
            elif use_faster_whisper:
                return FasterWhisper(model=model, language=language, **common_args)
            elif use_openai_transcription_api:
                return RemoteOpenaiTranscriber(model=openai_transcription_model,
                                               language=language,
                                               proxy=processing_proxy,
                                               **common_args)
            else:
                return OpenaiWhisper(model=model, language=language, **common_args)

        transcriber_future = executor.submit(init_transcriber)

        def init_translator():
            if not translation_prompt:
                return None
            import json as _json
            glossary = {}
            if translation_glossary:
                try:
                    glossary = _json.loads(translation_glossary)
                    if not isinstance(glossary, dict):
                        glossary = {}
                except (ValueError, TypeError):
                    pass
            if google_api_key:
                llm_client = LLMClient(
                    llm_type=LLMClient.LLM_TYPE.GEMINI,
                    model=gemini_model,
                    prompt=translation_prompt,
                    history_size=translation_history_size,
                    proxy=processing_proxy,
                    use_json_result=use_json_result,
                    gemini_base_url=gemini_base_url,
                    glossary=glossary,
                )
            else:
                llm_client = LLMClient(
                    llm_type=LLMClient.LLM_TYPE.GPT,
                    model=gpt_model,
                    prompt=translation_prompt,
                    history_size=translation_history_size,
                    proxy=processing_proxy,
                    use_json_result=use_json_result,
                    glossary=glossary,
                )
            if translation_history_size == 0:
                return ParallelTranslator(
                    llm_client=llm_client,
                    timeout=translation_timeout,
                    retry_if_translation_fails=retry_if_translation_fails,
                )
            else:
                return SerialTranslator(
                    llm_client=llm_client,
                    timeout=translation_timeout,
                    retry_if_translation_fails=retry_if_translation_fails,
                )

        translator_future = executor.submit(init_translator)
        exporter_future = executor.submit(
            ResultExporter,
            cqhttp_url=cqhttp_url,
            cqhttp_token=cqhttp_token,
            discord_webhook_url=discord_webhook_url,
            telegram_token=telegram_token,
            telegram_chat_id=telegram_chat_id,
            output_file_path=output_file_path,
            proxy=output_proxy,
            output_whisper_result=not hide_transcribe_result,
            output_timestamps=output_timestamps,
            subtitle_share_push_url=subtitle_share_push_url,
            subtitle_share_token=subtitle_share_token,
            show_latency_log=show_latency_log,
        )

        audio_getter = audio_getter_future.result()
        slicer = slicer_future.result()
        transcriber = transcriber_future.result()
        translator = translator_future.result()
        exporter = exporter_future.result()

    if hasattr(audio_getter, '_exit_handler'):
        signal.signal(signal.SIGINT, audio_getter._exit_handler)

    print(f'{INFO}Initialization complete, starting up...')

    # Start working
    start_daemon_thread(audio_getter.loop, output_queue=getter_to_slicer_queue)
    start_daemon_thread(
        slicer.loop,
        input_queue=getter_to_slicer_queue,
        output_queue=slicer_to_transcriber_queue,
    )
    start_daemon_thread(
        transcriber.loop,
        input_queue=slicer_to_transcriber_queue,
        output_queue=transcriber_to_translator_queue,
    )
    if translator:
        start_daemon_thread(
            translator.loop,
            input_queue=transcriber_to_translator_queue,
            output_queue=translator_to_exporter_queue,
        )
    exporter_thread = start_daemon_thread(
        exporter.loop,
        input_queue=translator_to_exporter_queue,
    )

    try:
        while exporter_thread.is_alive():
            time.sleep(1)
    finally:
        if managed_subtitle_share_server:
            if managed_subtitle_share_task_id:
                managed_subtitle_share_server.finish_task(managed_subtitle_share_task_id, 0)
                time.sleep(0.2)
            managed_subtitle_share_server.stop()
    print(f'{INFO}All processing completed, program exits.')


def _start_subtitle_share_server(host: str, port: int):
    server = SubtitleShareServer(host=host, port=port, enabled=True)
    server.start()
    print(f'{INFO}Subtitle sharing server started on {host}:{server.port}')
    print(f'{INFO}Subtitle sharing API: http://127.0.0.1:{server.port}/api/server/info')
    print(f'{INFO}Live subtitles page: http://127.0.0.1:{server.port}/')
    return server


def _run_preloaded_task(url: str, args: dict, manager: PreloadedTranscriberManager,
                        share_server: SubtitleShareServer | None = None) -> int:
    config = build_asr_config(args)
    transcriber = manager.get_for_run(config)
    controller = PipelineController()
    result = {"code": 0, "error": None}
    local_share_server = None
    task_id = None
    push_url = None
    push_token = None

    try:
        active_share_server = share_server
        if active_share_server is None and args.get("enable_subtitle_sharing"):
            active_share_server = _start_subtitle_share_server(args.get("subtitle_share_host", DEFAULT_PUBLIC_HOST),
                                                               args.get("subtitle_share_public_port", DEFAULT_PUBLIC_PORT))
            local_share_server = active_share_server

        if active_share_server is not None:
            task_id = create_task_id()
            active_share_server.begin_task(task_id, os.getpid())
            push_url = f'http://127.0.0.1:{active_share_server.port}/api/translation/push/{task_id}'
            push_token = active_share_server.push_token
            print(f'{INFO}Subtitle sharing task ID: {task_id}')

        def worker():
            try:
                result["code"] = run_inprocess_pipeline(url,
                                                        args,
                                                        transcriber,
                                                        controller=controller,
                                                        subtitle_share_push_url=push_url,
                                                        subtitle_share_token=push_token)
            except Exception as e:
                result["error"] = e
                result["code"] = 1

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        while thread.is_alive():
            try:
                thread.join(timeout=0.2)
            except KeyboardInterrupt:
                print(f'{WARNING}Stopping current task. The preloaded ASR model will stay loaded.')
                controller.request_stop()
        if result["error"] is not None:
            raise result["error"]
        return int(result["code"] or 0)
    finally:
        if share_server is not None and task_id:
            share_server.finish_task(task_id, result["code"])
        if local_share_server is not None:
            if task_id:
                local_share_server.finish_task(task_id, result["code"])
                time.sleep(0.2)
            local_share_server.stop()
        manager.release()


def run_preloaded_cli(url: str, args: dict) -> None:
    manager = PreloadedTranscriberManager()
    config = build_asr_config(args)
    print(f"{INFO}{manager.preload(config)}")

    keep_loaded = bool(args.get("keep_asr_loaded"))
    share_server = None
    try:
        if keep_loaded and args.get("enable_subtitle_sharing"):
            share_server = _start_subtitle_share_server(args.get("subtitle_share_host", DEFAULT_PUBLIC_HOST),
                                                        args.get("subtitle_share_public_port", DEFAULT_PUBLIC_PORT))

        next_url = url
        while next_url:
            _run_preloaded_task(next_url, args, manager, share_server=share_server)
            if not keep_loaded:
                break
            try:
                next_url = input("Next URL> ").strip()
            except KeyboardInterrupt:
                print()
                break
            if not next_url or next_url.lower() == "exit":
                break
    finally:
        if share_server is not None:
            share_server.stop()
        print(f"{INFO}{manager.unload()}")


def cli():
    print(f'{INFO}Version: {__version__}')
    parser = argparse.ArgumentParser(description='Parameters for translator.py')
    parser.add_argument(
        'URL',
        type=str,
        help=
        'The URL of the stream. If a local file path is filled in, it will be used as input. If fill in "device", the input will be obtained from your PC device.'
    )
    parser.add_argument(
        '--openai_api_key',
        type=str,
        default=None,
        help=
        'OpenAI API key if using GPT translation / Whisper API. If you have multiple keys, you can separate them with \",\" and each key will be used in turn.'
    )
    parser.add_argument(
        '--google_api_key',
        type=str,
        default=None,
        help=
        'Google API key if using Gemini translation. If you have multiple keys, you can separate them with \",\" and each key will be used in turn.'
    )
    parser.add_argument('--openai_base_url',
                        type=str,
                        default=None,
                        help='Customize the API endpoint of OpenAI (Affects GPT translation & OpenAI Transcription).')
    parser.add_argument('--google_base_url',
                        type=str,
                        default=None,
                        help='Customize the API endpoint of Google (Affects Gemini translation).')
    parser.add_argument('--gpt_base_url', type=str, default=None, help='(Deprecated) Use --openai_base_url instead.')
    parser.add_argument('--gemini_base_url', type=str, default=None, help='(Deprecated) Use --google_base_url instead.')
    parser.add_argument('--proxy',
                        type=str,
                        default=None,
                        help='Used to set the proxy for all --*_proxy flags if they are not specifically set.')
    parser.add_argument(
        '--format',
        type=str,
        default='ba/wa*',
        help=
        'Stream format code, this parameter will be passed directly to yt-dlp. You can get the list of available format codes by \"yt-dlp {url} -F\"'
    )
    parser.add_argument('--list_format', action='store_true', help='Print all available formats then exit.')
    parser.add_argument('--cookies',
                        type=str,
                        default=None,
                        help='Used to open member-only stream, this parameter will be passed directly to yt-dlp.')

    parser.add_argument('--input_proxy',
                        type=str,
                        default=None,
                        help='Use the specified HTTP/HTTPS/SOCKS proxy for yt-dlp, e.g. http://127.0.0.1:7890.')
    parser.add_argument(
        '--device_index',
        type=int,
        default=None,
        help=
        'The index of the device that needs to be recorded. If not set, the system default recording device will be used.'
    )
    parser.add_argument(
        '--device_recording_interval',
        type=float,
        default=0.5,
        help=
        'The shorter the recording interval, the lower the latency, but it will increase CPU usage. It is recommended to set it between 0.1 and 1.0.'
    )
    parser.add_argument('--list_devices', action='store_true', help='Print all audio devices info then exit.')
    parser.add_argument('--mic', action='store_true', help='Use microphone instead of system audio (loopback).')
    parser.add_argument('--loopback', action='store_true', help='Directly capture system audio output (Windows WASAPI loopback).')

    parser.add_argument('--min_audio_length', type=float, default=0.5, help='Minimum slice audio length in seconds.')
    parser.add_argument('--max_audio_length', type=float, default=30.0, help='Maximum slice audio length in seconds.')
    parser.add_argument(
        '--target_audio_length',
        type=float,
        default=5.0,
        help=
        'When dynamic no speech threshold is enabled (enabled by default), the program will slice the audio as close to this length as possible.'
    )
    parser.add_argument(
        '--continuous_no_speech_threshold',
        type=float,
        default=1.0,
        help=
        'Slice if there is no speech during this number of seconds. If the dynamic no speech threshold is enabled (enabled by default), the actual threshold will be dynamically adjusted based on this value.'
    )
    parser.add_argument('--disable_dynamic_no_speech_threshold',
                        action='store_true',
                        help='Set this flag to disable dynamic no speech threshold.')
    parser.add_argument('--prefix_retention_length',
                        type=float,
                        default=0.5,
                        help='The length of the retention prefix audio during slicing.')
    parser.add_argument(
        '--vad_threshold',
        type=float,
        default=0.35,
        help=
        'Range 0~1. the higher this value, the stricter the speech judgment. If dynamic VAD threshold is enabled (enabled by default), this threshold will be adjusted dynamically based on this value.'
    )
    parser.add_argument('--disable_dynamic_vad_threshold',
                        action='store_true',
                        help='Set this flag to disable dynamic VAD threshold.')
    parser.add_argument('--vad_backend',
                        type=str,
                        choices=['silero', 'firered'],
                        default='silero',
                        help='VAD backend used for audio slicing. FireRedVAD requires the omnivad library.')
    parser.add_argument('--firered_vad_model_path',
                        type=str,
                        default=None,
                        help='Optional OmniVAD FireRedVAD .omnivad model path. If omitted, the bundled OmniVAD model is used.')
    parser.add_argument(
        '--model',
        type=str,
        default='turbo',
        help=
        'Select Whisper/Faster-Whisper/Simul Streaming model size. See https://github.com/openai/whisper#available-models-and-languages for available models.'
    )
    parser.add_argument(
        '--language',
        type=str,
        default='auto',
        help=
        'Language spoken in the stream. Default option is to auto detect the spoken language. See https://github.com/openai/whisper#available-models-and-languages for available languages.'
    )

    parser.add_argument(
        '--use_faster_whisper',
        action='store_true',
        help=
        'Set this flag to use Faster-Whisper instead of Whisper. If used with --use_simul_streaming, SimulStreaming with Faster-Whisper as the encoder will be used.'
    )
    parser.add_argument(
        '--use_simul_streaming',
        action='store_true',
        help=
        'Set this flag to use SimulStreaming instead of Whisper. If used with --use_faster_whisper, SimulStreaming with Faster-Whisper as the encoder will be used.'
    )
    parser.add_argument('--use_openai_transcription_api',
                        action='store_true',
                        help='Set this flag to use OpenAI transcription API instead of the original local Whipser.')
    parser.add_argument(
        '--openai_transcription_model',
        type=str,
        default='gpt-4o-mini-transcribe',
        help='OpenAI\'s transcription model name, whisper-1 / gpt-4o-mini-transcribe / gpt-4o-transcribe')
    parser.add_argument('--use_qwen3_asr', action='store_true', help='Set this flag to use Qwen3-ASR.')
    parser.add_argument('--qwen3_context', type=str, default=None, help='Initial context / terms for Qwen3-ASR.')
    parser.add_argument('--qwen3_dtype', type=str, default='bfloat16', help='Dtype for Qwen3-ASR.')
    parser.add_argument('--qwen3_load_in_4bit', action='store_true', help='Load Qwen3-ASR model in 4-bit.')
    parser.add_argument(
        '--qwen3_rms_threshold',
        type=float,
        default=0.005,
        help='RMS volume threshold for Qwen3-ASR silence filtering. Audio segments with RMS below this will be ignored to prevent hallucinations.'
    )

    parser.add_argument('--use_hf_asr', action='store_true', help='Set this flag to use a HuggingFace ASR model specified by --model.')
    parser.add_argument('--use_nemo_asr', action='store_true', help='Set this flag to use NVIDIA NeMo ASR.')
    parser.add_argument('--nemo_asr_model', type=str, default='nvidia/parakeet-tdt_ctc-0.6b-ja', help='NeMo ASR model name.')
    parser.add_argument('--nemo_asr_device', type=str, default='auto', help='Device used when running NeMo ASR.')
    parser.add_argument('--nemo_asr_decoding', type=str, choices=['tdt', 'ctc'], default='tdt', help='Decoding mode for NeMo ASR.')

    parser.add_argument('--qwen3_asr_model', type=str, default=None, help='Override --model for Qwen3-ASR.')
    parser.add_argument('--qwen3_asr_dtype', type=str, default=None, help='Override --qwen3_dtype.')
    parser.add_argument('--qwen3_asr_device_map', type=str, default=None, help='Override device map for Qwen3-ASR.')
    parser.add_argument('--qwen3_asr_max_new_tokens', type=int, default=None, help='Override max new tokens for Qwen3-ASR.')
    parser.add_argument('--qwen3_asr_quantization', type=str, choices=['none', 'bnb_8bit', 'bnb_4bit'], default=None, help='Quantization for Qwen3-ASR.')
    parser.add_argument('--qwen3_asr_bnb_4bit_quant_type', type=str, choices=['nf4', 'fp4'], default=None, help='4-bit quant type.')
    parser.add_argument('--qwen3_asr_bnb_4bit_use_double_quant', action='store_true', help='Double quant for Qwen3-ASR.')
    parser.add_argument('--runtime_profile', type=str, choices=['cuda', 'cpu', 'rocm'], default='cuda', help='Runtime profile used to select local ASR accelerator policy.')
    parser.add_argument('--runtime_device_policy', type=str, choices=['auto_discrete', 'auto_any', 'manual', 'cpu'], default='auto_discrete', help='Device selection policy for local ASR backends.')
    parser.add_argument('--runtime_allow_integrated_gpu', action='store_true', help='Allow integrated GPUs for experimental local ASR acceleration.')

    parser.add_argument(
        '--transcription_filters',
        type=str,
        default='emoji_filter,repetition_filter',
        help=
        'Filters apply to transcription results, separated by ",". We provide emoji_filter, repetition_filter and japanese_stream_filter.'
    )
    parser.add_argument(
        '--whisper_filters',
        type=str,
        default=None,
        help='(Deprecated) Use --transcription_filters instead.'
    )
    parser.add_argument(
        '--transcription_initial_prompt',
        type=str,
        default=None,
        help='General purpose prompt or glossary for transcription. Format: "Word1, Word2, Word3, ...".')
    parser.add_argument('--disable_transcription_context',
                        action='store_true',
                        help='Set this flag to disable context (previous sentence) propagation in transcription.')
    parser.add_argument('--asr_corrections_enabled', action='store_true',
                        help='Apply ASR proper-noun correction rules after transcription.')
    parser.add_argument('--asr_correction_rules', type=str, default=None,
                        help='JSON list of ASR correction rules with canonical and aliases fields.')
    parser.add_argument('--asr_corrections_case_sensitive', action='store_true',
                        help='Match ASR correction aliases case-sensitively.')
    parser.add_argument('--gpt_model',
                        type=str,
                        default='gpt-5-nano',
                        help='OpenAI\'s GPT model name, gpt-5 / gpt-5-mini / gpt-5-nano')
    parser.add_argument('--gemini_model',
                        type=str,
                        default='gemini-2.5-flash-lite',
                        help='Google\'s Gemini model name, gemini-2.0-flash / gemini-2.5-flash / gemini-2.5-flash-lite')
    parser.add_argument(
        '--translation_prompt',
        type=str,
        default=None,
        help=
        'If set, will translate result text to target language via GPT / Gemini API. Example: \"Translate from Japanese to Chinese\"'
    )
    parser.add_argument(
        '--translation_glossary',
        type=str,
        default=None,
        help='Terminology glossary as a JSON string, e.g. \'{"FPS":"每秒幀數","CPU":"中央處理器"}\'.'
    )
    parser.add_argument(
        '--translation_history_size',
        type=int,
        default=0,
        help=
        'The number of previous messages sent when calling the GPT / Gemini API. If the history size is 0, the translation will be run parallelly. If the history size > 0, the translation will be run serially.'
    )
    parser.add_argument(
        '--translation_timeout',
        type=int,
        default=10,
        help='If the GPT / Gemini translation exceeds this number of seconds, the translation will be discarded.')
    parser.add_argument(
        '--processing_proxy',
        type=str,
        default=None,
        help=
        'Use the specified HTTP/HTTPS/SOCKS proxy for Whisper/GPT API (Gemini currently doesn\'t support specifying a proxy within the program), e.g. http://127.0.0.1:7890.'
    )
    parser.add_argument('--use_json_result',
                        action='store_true',
                        help='Using JSON result in LLM translation for some locally deployed models.')
    parser.add_argument('--retry_if_translation_fails',
                        action='store_true',
                        help='Retry when translation times out/fails. Used to generate subtitles offline.')
    parser.add_argument('--output_timestamps',
                        action='store_true',
                        help='Output the timestamp of the text when outputting the text.')
    parser.add_argument('--show_latency_log',
                        action='store_true',
                        help='Print ASR and LLM latency in terminal logs.')
    parser.add_argument('--hide_transcribe_result', action='store_true', help='Hide the result of Whisper transcribe.')
    parser.add_argument(
        '--output_proxy',
        type=str,
        default=None,
        help='Use the specified HTTP/HTTPS/SOCKS proxy for Cqhttp/Discord/Telegram, e.g. http://127.0.0.1:7890.')
    parser.add_argument('--output_file_path',
                        type=str,
                        default=None,
                        help='If set, will save the result text to this path.')
    parser.add_argument('--cqhttp_url',
                        type=str,
                        default=None,
                        help='If set, will send the result text to this Cqhttp server.')
    parser.add_argument('--cqhttp_token',
                        type=str,
                        default=None,
                        help='Token of cqhttp, if it is not set on the server side, it does not need to fill in.')
    parser.add_argument('--discord_webhook_url',
                        type=str,
                        default=None,
                        help='If set, will send the result text to this Discord channel.')
    parser.add_argument('--telegram_token', type=str, default=None, help='Token of Telegram bot.')
    parser.add_argument(
        '--telegram_chat_id',
        type=int,
        default=None,
        help='If set, will send the result text to this Telegram chat. Needs to be used with \"--telegram_token\".')
    parser.add_argument('--enable_subtitle_sharing',
                        action='store_true',
                        help='Start a public SSE subtitle sharing server from the CLI process.')
    parser.add_argument('--subtitle_share_public_port',
                        type=int,
                        default=DEFAULT_PUBLIC_PORT,
                        help='Public subtitle sharing port used with --enable_subtitle_sharing.')
    parser.add_argument('--subtitle_share_host',
                        type=str,
                        default=DEFAULT_PUBLIC_HOST,
                        help='Host/IP to bind the subtitle sharing server. Defaults to 0.0.0.0.')
    parser.add_argument('--preload_asr_model',
                        action='store_true',
                        help='Preload the selected local ASR model before running.')
    parser.add_argument('--keep_asr_loaded',
                        action='store_true',
                        help='Keep the preloaded ASR model loaded and prompt for the next URL after each task.')

    args = parser.parse_args().__dict__

    url = args.pop('URL')
    loopback = args.pop('loopback', False)

    if url.lower() != 'device' and loopback is False and url.lower() != 'loopback' and not shutil.which('ffmpeg'):
        if platform.system() == 'Windows':
            print(f'{ERROR}ffmpeg not found. Please install it with: winget install ffmpeg')
        else:
            print(f'{ERROR}ffmpeg not found. Please install it with: sudo apt install ffmpeg')
        sys.exit(1)

    if args['proxy']:
        os.environ['http_proxy'] = args['proxy']
        os.environ['https_proxy'] = args['proxy']
        os.environ['HTTP_PROXY'] = args['proxy']
        os.environ['HTTPS_PROXY'] = args['proxy']
        if args['input_proxy'] is None:
            args['input_proxy'] = args['proxy']
        if args['processing_proxy'] is None:
            args['processing_proxy'] = args['proxy']
        if args['output_proxy'] is None:
            args['output_proxy'] = args['proxy']

    # 處理 loopback 模式的前置檢查
    if loopback or url.lower() == 'loopback':
        if sys.platform != 'win32':
            print(f'{ERROR}WASAPI Loopback 僅支援 Windows 平台。')
            print(f'{INFO}請提供 URL、檔案路徑或使用以下指令查看設備：')
            print(f'  python -m stream_translator_gpt device --list_devices')
            sys.exit(1)
        try:
            import pyaudiowpatch
            print(f'{INFO}已啟用 WASAPI Loopback 模式，將捕獲系統音頻輸出。')
        except ImportError:
            print(f'{WARNING}pyaudiowpatch 未安裝，無法使用 Loopback 功能。')
            print(f'{INFO}安裝方法：pip install pyaudiowpatch')
            print(f'{INFO}或者請提供 URL、檔案路徑或使用 "device" 參數。')
            sys.exit(1)
    
    if args['list_devices']:
        if platform.system() == 'Windows':
            import pyaudiowpatch as pa
        else:
            try:
                import pyaudio as pa
            except ImportError:
                print("PyAudio is not installed. Unable to list devices.")
                print("Debian/Ubuntu/Colab: apt install portaudio19-dev && pip install pyaudio")
                exit(1)
        pyaudio = pa.PyAudio()
        print("Available audio devices:")
        for i in range(pyaudio.get_device_count()):
            dev = pyaudio.get_device_info_by_index(i)
            if dev.get('maxInputChannels') > 0:
                print(f"{dev['index']}: {dev['name']}")
        if platform.system() == 'Windows':
            print("\nLoopback devices (for system audio):")
            for loopback_dev in pyaudio.get_loopback_device_info_generator():
                print(f"{loopback_dev['index']}: {loopback_dev['name']}")
        pyaudio.terminate()
        exit(0)

    if args['list_format']:
        if args.get('loopback') or url.lower() == 'loopback':
            print(f'{ERROR}--list_format 需要指定有效的 URL 參數（不能是 loopback 模式）。')
            sys.exit(1)
        cmd = ['yt-dlp', url, '-F']
        _append_site_specific_ytdlp_args(cmd, url)
        cookie_file = _resolve_cookie_file(url, args['cookies'])
        if cookie_file:
            cmd.extend(['--cookies', cookie_file])
        if args['input_proxy']:
            cmd.extend(['--proxy', args['input_proxy']])
        subprocess.run(cmd)
        exit(0)

    if args['model'].endswith('.en'):
        if args['model'] == 'large.en':
            print(
                f'{ERROR}English model does not have large model, please choose from {{tiny.en, small.en, medium.en}}')
            sys.exit(1)
        if args['language'] != 'English' and args['language'] != 'en':
            if args['language'] == 'auto':
                print(f'{WARNING}Using .en model, setting language from auto to English')
                args['language'] = 'en'
            else:
                print(
                    f'{ERROR}English model cannot be used to detect non english language, please choose a non .en model'
                )
                sys.exit(1)

    transcription_encoder_flag_num = 0
    transcription_decoder_flag_num = 0
    if args['use_faster_whisper']:
        transcription_encoder_flag_num += 1
    if args['use_simul_streaming']:
        transcription_decoder_flag_num += 1
    if args['use_openai_transcription_api']:
        transcription_encoder_flag_num += 1
        transcription_decoder_flag_num += 1
    if args['use_qwen3_asr']:
        transcription_encoder_flag_num += 1
        transcription_decoder_flag_num += 1
    if args['use_hf_asr']:
        transcription_encoder_flag_num += 1
        transcription_decoder_flag_num += 1
    if args['use_nemo_asr']:
        transcription_encoder_flag_num += 1
        transcription_decoder_flag_num += 1

    if transcription_encoder_flag_num > 1:
        print(f'{ERROR}Cannot use multiple transcription encoder backends at the same time')
        sys.exit(1)
    if transcription_decoder_flag_num > 1:
        print(f'{ERROR}Cannot use multiple transcription decoder backends at the same time')
        sys.exit(1)

    if args['use_openai_transcription_api'] and not args['openai_api_key']:
        print(f'{ERROR}Please fill in the OpenAI API key when enabling OpenAI Transcription API')
        sys.exit(1)

    if args['keep_asr_loaded'] and not args['preload_asr_model']:
        print(f'{ERROR}--keep_asr_loaded requires --preload_asr_model')
        sys.exit(1)

    if args['preload_asr_model'] and args['use_openai_transcription_api']:
        print(f'{ERROR}OpenAI Transcription API is remote and does not need ASR preloading')
        sys.exit(1)

    if args['translation_prompt'] and not (args['openai_api_key'] or args['google_api_key']):
        print(f'{ERROR}Please fill in the OpenAI / Google API key when enabling LLM translation')
        sys.exit(1)

    if args['gpt_base_url'] is not None:
        print(
            f'{WARNING}--gpt_base_url is deprecated and will be removed in future versions. Please use --openai_base_url instead.'
        )
        if args['openai_base_url'] is None:
            args['openai_base_url'] = args['gpt_base_url']

    if args['gemini_base_url'] is not None:
        print(
            f'{WARNING}--gemini_base_url is deprecated and will be removed in future versions. Please use --google_base_url instead.'
        )
        if args['google_base_url'] is None:
            args['google_base_url'] = args['gemini_base_url']

    args.pop('gpt_base_url', None)
    args.pop('gemini_base_url', None)

    if args['language'] == 'auto':
        args['language'] = None

    if args['whisper_filters'] is not None:
        print(
            f'{WARNING}--whisper_filters is deprecated and will be removed in future versions. Please use --transcription_filters instead.'
        )
        if args['transcription_filters'] == 'emoji_filter,repetition_filter':
            args['transcription_filters'] = args['whisper_filters']
    args.pop('whisper_filters', None)

    args.pop('list_format', None)
    args.pop('list_devices', None)

    if args['output_file_path']:
        output_dir = os.path.dirname(os.path.abspath(args['output_file_path']))
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(f'{INFO}Created output directory: {output_dir}')

    preload_asr_model = args.pop('preload_asr_model', False)
    keep_asr_loaded = args.pop('keep_asr_loaded', False)
    if preload_asr_model:
        args['keep_asr_loaded'] = keep_asr_loaded
        args['loopback'] = loopback
        run_preloaded_cli(url, args)
        return

    main(url, loopback=loopback, **args)


if __name__ == '__main__':
    cli()
