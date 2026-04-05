import argparse
import os
import queue
import signal
import sys
import time
import subprocess
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
from .audio_transcriber import OpenaiWhisper, FasterWhisper, SimulStreaming, RemoteOpenaiTranscriber, Qwen3ASR
from .llm_translator import LLMClient, ParallelTranslator, SerialTranslator
from .result_exporter import ResultExporter
from . import __version__


def main(url, proxy, openai_api_key, google_api_key, format, cookies, input_proxy, device_index,
         device_recording_interval, min_audio_length, max_audio_length, target_audio_length,
         continuous_no_speech_threshold, disable_dynamic_no_speech_threshold, prefix_retention_length, vad_threshold,
         disable_dynamic_vad_threshold, model, language, use_faster_whisper, use_simul_streaming,
         use_openai_transcription_api, use_qwen3_asr, openai_transcription_model, whisper_filters, disable_transcription_context,
         transcription_initial_prompt, qwen3_context, qwen3_dtype, qwen3_load_in_4bit,
         translation_prompt, translation_history_size, gpt_model, gemini_model,
         translation_timeout, gpt_base_url, gemini_base_url, processing_proxy, use_json_result,
         retry_if_translation_fails, output_timestamps, hide_transcribe_result, output_proxy, output_file_path,
         cqhttp_url, cqhttp_token, discord_webhook_url, telegram_token, telegram_chat_id,
         translation_glossary=None, loopback=False,
         vad_every_n_frames: int = 1, realtime_processing: bool = False):
    if gpt_base_url:
        os.environ['OPENAI_BASE_URL'] = gpt_base_url

    ApiKeyPool.init(openai_api_key=openai_api_key, google_api_key=google_api_key)

    # Init queues
    getter_to_slicer_queue = queue.SimpleQueue()
    slicer_to_transcriber_queue = queue.SimpleQueue()
    transcriber_to_translator_queue = queue.SimpleQueue()
    translator_to_exporter_queue = queue.SimpleQueue() if translation_prompt else transcriber_to_translator_queue

    # Init workers
    with ThreadPoolExecutor() as executor:

        def init_audio_getter():
            # 自動模式：使用 --loopback 或 URL="loopback" 時自動捕獲系統音頻
            if loopback or url.lower() == 'loopback':
                import sys
                if sys.platform == 'win32':
                    print(f'{INFO}自動捕獲模式：使用 WASAPI Loopback 捕獲系統預設播放設備音頻。')
                    return DeviceAudioGetter(
                        device_index=device_index,
                        recording_interval=device_recording_interval,
                        use_loopback=True,  # 自動啟用 loopback
                    )
                else:
                    print(f'{ERROR}WASAPI Loopback 僅支援 Windows 平台。')
                    print(f'{INFO}請提供 URL、檔案路徑或使用 "device" 參數。')
                    sys.exit(1)
            elif url.lower() == 'device':
                return DeviceAudioGetter(
                    device_index=device_index,
                    recording_interval=device_recording_interval,
                    use_loopback=False,  # device 模式預設不使用 loopback
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
            disable_vad=False,  # 所有 ASR 引擎都應使用 VAD 過濾靜音，避免幻覺輸出
        )

        def init_transcriber():
            common_args = {
                'whisper_filters': whisper_filters,
                'print_result': not hide_transcribe_result,
                'output_timestamps': output_timestamps,
                'disable_transcription_context': disable_transcription_context,
                'transcription_initial_prompt': transcription_initial_prompt,
            }
            if use_qwen3_asr:
                return Qwen3ASR(model=model, language=language, context=qwen3_context,
                                dtype=qwen3_dtype, load_in_4bit=qwen3_load_in_4bit, **common_args)
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
            # 解析術語表 JSON 字串（來自 --translation_glossary）
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

    while exporter_thread.is_alive():
        time.sleep(1)
    print(f'{INFO}All processing completed, program exits.')


def cli():
    print(f'{INFO}Version: {__version__}')
    parser = argparse.ArgumentParser(description='Parameters for translator.py')
    parser.add_argument(
        'URL',
        type=str,
        nargs='?',
        default='loopback',
        help=
        'The URL of the stream. If a local file path is filled in, it will be used as input. If fill in "device", the input will be obtained from your PC device. If not provided or use "loopback", will auto-capture system audio using WASAPI loopback (Windows only).'
    )
    parser.add_argument('--proxy',
                        type=str,
                        default=None,
                        help='Used to set the proxy for all --*_proxy flags if they are not specifically set.')
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
    parser.add_argument(
        '--format',
        type=str,
        default='ba/wa*',
        help=
        'Stream format code, this parameter will be passed directly to yt-dlp. You can get the list of available format codes by \"yt-dlp \{url\} -F\"'
    )
    parser.add_argument('--list_format', action='store_true', help='Print all available formats then exit.')
    parser.add_argument('--cookies',
                        type=str,
                        default=None,
                        help='Used to open member-only stream, this parameter will be passed directly to yt-dlp.')

    parser.add_argument('--input_proxy',
                        type=str,
                        default=None,
                        help='Use the specified HTTP/HTTPS/SOCKS proxy for yt-dlp, '
                        'e.g. http://127.0.0.1:7890.')
    parser.add_argument(
        '--device_index',
        type=int,
        default=None,
        help=
        'The index of the device that needs to be recorded. If not set, the system default recording device will be used.'
    )
    parser.add_argument('--list_devices', action='store_true', help='Print all audio devices info then exit.')
    parser.add_argument(
        '--loopback',
        action='store_true',
        help='Auto-capture system audio using WASAPI loopback (Windows only, requires pyaudiowpatch). Equivalent to not providing URL or URL="loopback". This allows capturing audio without enabling "Stereo Mix".'
    )

    parser.add_argument(
        '--device_recording_interval',
        type=float,
        default=0.5,
        help=
        'The shorter the recording interval, the lower the latency, but it will increase CPU usage. It is recommended to set it between 0.1 and 1.0.'
    )
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
        'Range 0~1. the higher this value, the stricter the speech judgment. If dynamic VAD threshold is enabled (enabled by default), this threshold will be adjusted dynamically based on the input speech\'s VAD results.'
    )
    parser.add_argument('--disable_dynamic_vad_threshold',
                        action='store_true',
                        help='Set this flag to disable dynamic VAD threshold.')
    parser.add_argument(
        '--vad_every_n_frames',
        type=int,
        default=1,
        help=
        'Run VAD inference only once every N audio frames (default: 1 = every frame). '
        'For non-live sources (local files / non-live URLs) set to 2 or 3 to cut VAD CPU usage roughly in half or to one-third. '
        'Frames that are skipped reuse the previous frame\'s speech probability, so transitions from speech → silence are detected up to N×32 ms later (barely noticeable).'
    )
    parser.add_argument(
        '--realtime_processing',
        action='store_true',
        help=
        'Throttle audio reading to real-time speed for local files / non-live URLs. '
        'This caps CPU usage to the same level as live streaming but processing will not finish faster than the audio duration.'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='small',
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
        '--use_qwen3_asr',
        action='store_true',
        help='Set this flag to use Qwen3-ASR instead of Whisper.'
    )
    parser.add_argument(
        '--qwen3_context',
        type=str,
        default=None,
        help='Context text for Qwen3-ASR (e.g., terminology glossary, technical terms). This will be passed via system message to improve transcription accuracy.'
    )
    parser.add_argument(
        '--qwen3_dtype',
        type=str,
        default='bfloat16',
        choices=['bfloat16', 'float16', 'float32'],
        help='Data type for Qwen3-ASR model weights.'
    )
    parser.add_argument(
        '--qwen3_load_in_4bit',
        action='store_true',
        help='Load Qwen3-ASR model in 4-bit quantization using bitsandbytes (NF4). Reduces VRAM from ~3.5GB to ~1.3GB. Requires: pip install bitsandbytes'
    )
    parser.add_argument(
        '--openai_transcription_model',
        type=str,
        default='gpt-4o-mini-transcribe',
        help='OpenAI\'s transcription model name, whisper-1 / gpt-4o-mini-transcribe / gpt-4o-transcribe')
    parser.add_argument(
        '--whisper_filters',
        type=str,
        default='emoji_filter,repetition_filter',
        help=
        'Filters apply to whisper results, separated by ",". We provide emoji_filter, repetition_filter and japanese_stream_filter.'
    )
    parser.add_argument(
        '--transcription_initial_prompt',
        type=str,
        default=None,
        help='General purpose prompt or glossary for transcription. Format: "Word1, Word2, Word3, ...".')
    parser.add_argument('--disable_transcription_context',
                        action='store_true',
                        help='Set this flag to disable context (previous sentence) propagation in transcription.')
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
        help='Terminology glossary as a JSON string, e.g. \'{"FPS":"每秒幀數","CPU":"中央處理器"}\'. '
             'Only terms that appear in the current transcript are injected into the prompt, '
             'saving tokens when the glossary is large.'
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
    parser.add_argument('--gpt_base_url', type=str, default=None, help='Customize the API endpoint of GPT.')
    parser.add_argument('--gemini_base_url', type=str, default=None, help='Customize the API endpoint of Gemini.')
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

    args = parser.parse_args().__dict__

    url = args.pop('URL')
    loopback = args.pop('loopback', False)

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
        import sys
        if sys.platform != 'win32':
            print(f'{ERROR}WASAPI Loopback 僅支援 Windows 平台。')
            print(f'{INFO}請提供 URL、檔案路徑或使用以下指令查看設備：')
            print(f'  python -m stream_translator_gpt device --list_devices')
            sys.exit(1)
        # 檢查 pyaudiowpatch 是否可用
        try:
            import pyaudiowpatch
            print(f'{INFO}已啟用 WASAPI Loopback 模式，將捕獲系統音頻輸出。')
        except ImportError:
            print(f'{WARNING}pyaudiowpatch 未安裝，無法使用 Loopback 功能。')
            print(f'{INFO}安裝方法：pip install pyaudiowpatch')
            print(f'{INFO}或者請提供 URL、檔案路徑或使用 "device" 參數。')
            sys.exit(1)
    
    if args['list_devices']:
        import sys
        import sounddevice as sd
        
        print("=== SoundDevice 設備列表 ===")
        print(sd.query_devices())
        
        # 如果是 Windows 且 pyaudiowpatch 可用，顯示 loopback 設備
        if sys.platform == 'win32':
            try:
                import pyaudiowpatch as pyaudio
                p = pyaudio.PyAudio()
                
                print("\n=== WASAPI Loopback 設備（系統音頻捕獲） ===")
                try:
                    wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
                    loopback_found = False
                    
                    for i in range(wasapi_info.get('deviceCount')):
                        device = p.get_device_info_by_host_api_device_index(
                            wasapi_info.get('index'), i
                        )
                        if device.get('maxInputChannels') > 0:
                            # 檢查是否為 loopback
                            is_loopback = 'loopback' in device.get('name', '').lower()
                            if is_loopback or device.get('maxOutputChannels') == 0:
                                print(f"  [{device.get('index')}] {device.get('name')} (Loopback)")
                                loopback_found = True
                    
                    if not loopback_found:
                        print("  未找到 loopback 設備。請確保系統有音頻輸出設備。")
                except Exception as e:
                    print(f"  查詢 WASAPI 設備時發生錯誤：{e}")
                finally:
                    p.terminate()
            except ImportError:
                print("\n提示：安裝 pyaudiowpatch 可啟用 WASAPI loopback 功能：")
                print("  pip install pyaudiowpatch")
        
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
            sys.exit(0)
        if args['language'] != 'English' and args['language'] != 'en':
            if args['language'] == 'auto':
                print(f'{WARNING}Using .en model, setting language from auto to English')
                args['language'] = 'en'
            else:
                print(
                    f'{ERROR}English model cannot be used to detect non english language, please choose a non .en model'
                )
                sys.exit(0)

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
    if transcription_encoder_flag_num > 1:
        print(f'{ERROR}Cannot use Faster Whisper, OpenAI Transcription API, or Qwen3-ASR at the same time')
        sys.exit(0)
    if transcription_decoder_flag_num > 1:
        print(f'{ERROR}Cannot use Simul Streaming, OpenAI Transcription API, or Qwen3-ASR at the same time')
        sys.exit(0)

    if args['use_openai_transcription_api'] and not args['openai_api_key']:
        print(f'{ERROR}Please fill in the OpenAI API key when enabling OpenAI Transcription API')
        sys.exit(0)

    if args['translation_prompt'] and not (args['openai_api_key'] or args['google_api_key']):
        print(f'{ERROR}Please fill in the OpenAI / Google API key when enabling LLM translation')
        sys.exit(0)

    if args['language'] == 'auto':
        args['language'] = None

    args.pop('list_format', None)
    args.pop('list_devices', None)
    main(url, loopback=loopback, **args)


if __name__ == '__main__':
    cli()
