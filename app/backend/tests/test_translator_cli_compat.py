import backend.core.translator as translator_module
from backend.core.translator import TranslationContext
import asyncio
import logging
import threading
import pytest


def test_extract_supported_cli_args_parses_help_output():
    help_text = "usage: __main__.py [--vad_every_n_frames VAD_EVERY_N_FRAMES] [--realtime_processing] [--qwen3_dtype {bfloat16,float16,float32}] [URL]"

    supported_args = translator_module._extract_supported_cli_args(help_text)

    assert supported_args == frozenset({
        'vad_every_n_frames',
        'realtime_processing',
        'qwen3_dtype',
    })


def test_build_command_skips_args_unsupported_by_runtime(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        '_get_supported_cli_args',
        lambda python_exe, cwd, **kwargs: frozenset({
            'openai_api_key',
            'use_qwen3_asr',
            'qwen3_dtype',
            'retry_if_translation_fails',
        })
    )

    context = TranslationContext(
        {
            'url': 'https://example.com/live',
            'openai_api_key': 'test-key',
            'use_qwen3_asr': True,
            'qwen3_dtype': 'bfloat16',
            'retry_if_translation_fails': True,
            'vad_every_n_frames': 3,
            'realtime_processing': True,
        },
        'task-1'
    )

    command = context._build_command()

    assert '--openai_api_key' in command
    assert '--use_qwen3_asr' in command
    assert '--qwen3_dtype' in command
    assert '--retry_if_translation_fails' in command
    assert '--vad_every_n_frames' not in command
    assert '--realtime_processing' not in command
    assert command[-1] == 'https://example.com/live'


def test_build_command_silently_ignores_app_only_keys_and_warns_for_unknown(monkeypatch, caplog):
    monkeypatch.setattr(translator_module, '_get_supported_cli_args', lambda python_exe, cwd, **kwargs: None)
    context = TranslationContext(
        {
            'backend': 'llama',
            'family_optimizer_auto': True,
            'loopback': True,
            'use_loopback': True,
            'unknown_option': True,
        },
        'app-only-args',
    )

    with caplog.at_level(logging.DEBUG):
        command = context._build_command()

    assert not any('Skipping unsupported CLI arg: backend' in r.message for r in caplog.records)
    assert not any('Skipping unsupported CLI arg: family_optimizer_auto' in r.message for r in caplog.records)
    assert not any('Skipping unsupported CLI arg: loopback' in r.message for r in caplog.records)
    assert not any('Skipping unsupported CLI arg: use_loopback' in r.message for r in caplog.records)
    assert any('Skipping unsupported CLI arg: unknown_option' in r.message for r in caplog.records)
    assert '--backend' not in command
    assert '--family_optimizer_auto' not in command
    assert '--loopback' not in command
    assert '--use_loopback' not in command


@pytest.mark.parametrize(('source_arg', 'new_arg'), [
    ('gpt_base_url', 'openai_base_url'),
    ('gemini_base_url', 'google_base_url'),
])
def test_build_command_uses_new_base_url_flag_when_supported(monkeypatch, source_arg, new_arg):
    monkeypatch.setattr(
        translator_module,
        '_get_supported_cli_args',
        lambda python_exe, cwd, **kwargs: frozenset({new_arg}),
    )
    context = TranslationContext({source_arg: 'https://api.example'}, 'new-base-url')

    command = context._build_command()

    assert f'--{new_arg}' in command
    assert f'--{source_arg}' not in command


@pytest.mark.parametrize(('source_arg', 'new_arg'), [
    ('gpt_base_url', 'openai_base_url'),
    ('gemini_base_url', 'google_base_url'),
])
def test_build_command_keeps_old_base_url_flag_when_new_flag_unsupported(monkeypatch, source_arg, new_arg):
    monkeypatch.setattr(
        translator_module,
        '_get_supported_cli_args',
        lambda python_exe, cwd, **kwargs: frozenset({source_arg}),
    )
    context = TranslationContext({source_arg: 'https://api.example'}, 'old-base-url')

    command = context._build_command()

    assert f'--{source_arg}' in command
    assert f'--{new_arg}' not in command


def test_build_command_keeps_args_when_runtime_capability_unknown(monkeypatch):
    monkeypatch.setattr(translator_module, '_get_supported_cli_args', lambda python_exe, cwd, **kwargs: None)

    context = TranslationContext(
        {
            'url': 'https://example.com/live',
            'vad_every_n_frames': 2,
            'retry_if_translation_fails': True,
        },
        'task-2'
    )

    command = context._build_command()

    assert '--vad_every_n_frames' in command
    assert '2' in command
    assert '--retry_if_translation_fails' in command


def test_redact_command_args_masks_secret_and_credential_url_flags():
    command = [
        '--proxy', 'http://user:password@proxy.example:8080',
        '--output_proxy', 'socks5://alice:pw@proxy.example:1080',
        '--cqhttp_url', 'https://bot.example/hook?token=cq-secret',
        '--cqhttp_token', 'cq-token-secret',
        '--discord_webhook_url', 'https://discord.example/webhook/discord-secret',
        '--telegram_token', 'telegram-secret',
        '--telegram_chat_id', 'chat-secret',
    ]

    redacted = translator_module._redact_command_args(command)

    assert len(redacted) == len(command)
    assert redacted[0::2] == command[0::2]
    assert all(value in ('<redacted>', '<redacted-url>') for value in redacted[1::2])
    assert not any(secret in str(redacted) for secret in (
        'password', 'alice', 'pw@', 'cq-secret', 'cq-token-secret',
        'discord-secret', 'telegram-secret', 'chat-secret',
    ))


def test_redact_command_args_masks_equals_form_and_urls():
    redacted = translator_module._redact_command_args([
        '--proxy=http://user:password@proxy.example',
        'https://user:password@example.com/live?token=secret',
        'https://example.com/live?access_token=secret',
        '--description', 'contains_proxy_and_token words',
    ])
    assert redacted == [
        '--proxy=<redacted>', '<redacted-url>', '<redacted-url>',
        '--description', 'contains_proxy_and_token words',
    ]


def test_redact_command_args_masks_credentials_for_non_http_schemes():
    redacted = translator_module._redact_command_args([
        'rtsp://camera:rtsp-pass@camera.example/live',
        'ftp://uploader:ftp-pass@files.example/upload',
    ])
    assert redacted == ['<redacted-url>', '<redacted-url>']


def test_engine_connection_error_logs_telegram_token_redacted(caplog):
    command = ['--telegram_token', '123456:telegram-secret']
    secrets = translator_module._collect_command_secrets(command)
    with caplog.at_level(logging.ERROR):
        translator_module._log_engine_output(
            'error',
            'HTTPSConnectionPool: /bot123456:telegram-secret/sendMessage failed',
            secrets,
            '[STDERR] ',
        )
    assert 'telegram-secret' not in caplog.text
    assert '/bot<redacted>/sendMessage' in caplog.text


def test_full_command_serialization_fallback_stays_masked(monkeypatch, caplog):
    command = ['--proxy', 'http://user:password@proxy.example', '--telegram_token', 'bot-secret']
    monkeypatch.setattr(translator_module.json, 'dumps', lambda *args, **kwargs: (_ for _ in ()).throw(TypeError()))
    with caplog.at_level(logging.INFO):
        translator_module._log_command_args(command)
    assert 'password' not in caplog.text
    assert 'bot-secret' not in caplog.text
    assert '<redacted>' in caplog.text


def test_translation_stop_does_not_block_event_loop():
    termination_started = threading.Event()
    release_termination = threading.Event()

    def blocking_termination():
        termination_started.set()
        assert release_termination.wait(timeout=2)

    async def scenario():
        context = TranslationContext({}, 'slow-stop')
        context.process = object()
        context._stop_processes = blocking_termination
        ticked = asyncio.Event()
        stop_task = asyncio.create_task(context.stop())
        try:
            assert await asyncio.to_thread(termination_started.wait, 1)
            ticked.set()
            await asyncio.wait_for(ticked.wait(), timeout=0.2)
            assert not stop_task.done()
        finally:
            release_termination.set()
        await stop_task

    asyncio.run(scenario())


import json
import os
from pathlib import Path
from types import SimpleNamespace


@pytest.fixture
def probe_runtime(monkeypatch, tmp_path):
    python = tmp_path / 'runtime/python.exe'
    python.parent.mkdir()
    python.write_bytes(b'python')
    version = python.parent / 'runtime-version.json'
    version.write_text('{}', encoding='utf-8')
    engine = python.parent / 'Lib/site-packages/stream_translator_gpt'
    engine.mkdir(parents=True)
    (engine / '__init__.py').write_text('VALUE = 1', encoding='utf-8')
    sherpa = python.parent / 'Lib/site-packages/sherpa_onnx'
    sherpa.mkdir()
    (sherpa / '__init__.py').write_text('VALUE = 1', encoding='utf-8')
    monkeypatch.setenv('STREAM_TRANSLATOR_LOG_DIR', str(tmp_path / 'logs'))
    calls = []
    result = SimpleNamespace(returncode=0, stdout='--model --language', stderr='')
    def run(*args, **kwargs):
        calls.append((args, kwargs))
        return result
    monkeypatch.setattr(translator_module.subprocess, 'run', run)
    return python, version, engine, calls, result


def test_cli_persistent_hit_and_identity_changes(probe_runtime, tmp_path):
    python, _, engine, calls, _ = probe_runtime
    def probe():
        return translator_module._get_supported_cli_args(str(python), str(tmp_path))
    assert probe() == frozenset({'model', 'language'})
    assert probe() == frozenset({'model', 'language'})
    assert len(calls) == 1
    stat = python.stat()
    os.utime(python, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    probe()
    assert len(calls) == 2
    (engine / '__init__.py').write_text('VALUE = 222', encoding='utf-8')
    probe()
    assert len(calls) == 3
    source = tmp_path / 'stream-translator-gpt/stream_translator_gpt'
    source.mkdir(parents=True)
    (source / '__init__.py').write_text('SOURCE = True', encoding='utf-8')
    probe()
    assert len(calls) == 4
    assert calls[-1][0][0][1] == '-c'


def test_cpu_cache_invalidated_by_runtime_version(probe_runtime):
    python, version, _, calls, _ = probe_runtime
    translator_module._validate_cpu_asr_runtime(str(python))
    translator_module._validate_cpu_asr_runtime(str(python))
    assert len(calls) == 1
    version.write_text('{"version": 2}', encoding='utf-8')
    translator_module._validate_cpu_asr_runtime(str(python))
    assert len(calls) == 2


@pytest.mark.parametrize('cpu', [False, True])
def test_probe_failures_never_cached(probe_runtime, tmp_path, cpu):
    python, _, _, calls, result = probe_runtime
    result.returncode = 1
    result.stdout = ''
    result.stderr = 'broken runtime'
    for _ in range(2):
        if cpu:
            with pytest.raises(RuntimeError, match='broken runtime'):
                translator_module._validate_cpu_asr_runtime(str(python))
        else:
            assert translator_module._get_supported_cli_args(str(python), str(tmp_path)) is None
    assert len(calls) == 2
    assert not (tmp_path / 'logs/engine_probe_cache.json').exists()


@pytest.mark.parametrize('cpu', [False, True])
def test_probe_exception_never_cached(probe_runtime, monkeypatch, tmp_path, cpu):
    python, _, _, calls, _ = probe_runtime
    def fail(*args, **kwargs):
        calls.append(None)
        raise OSError('cannot launch')
    monkeypatch.setattr(translator_module.subprocess, 'run', fail)
    for _ in range(2):
        if cpu:
            with pytest.raises(RuntimeError, match='CPU ASR sidecar'):
                translator_module._validate_cpu_asr_runtime(str(python))
        else:
            assert translator_module._get_supported_cli_args(str(python), str(tmp_path)) is None
    assert len(calls) == 2


def test_corrupt_probe_cache_is_replaced(probe_runtime, tmp_path):
    python, _, _, calls, _ = probe_runtime
    cache = tmp_path / 'logs/engine_probe_cache.json'
    cache.parent.mkdir()
    cache.write_bytes(b'\xffinvalid')
    translator_module._get_supported_cli_args(str(python), str(tmp_path))
    assert len(calls) == 1
    assert len(json.loads(cache.read_text(encoding='utf-8'))) == 1
    assert not list(cache.parent.glob('*.tmp'))


@pytest.mark.parametrize('cpu', [False, True])
def test_missing_fingerprint_disables_probe_cache(probe_runtime, monkeypatch, tmp_path, cpu):
    python, _, _, calls, _ = probe_runtime
    monkeypatch.setattr(translator_module, 'engine_fingerprint', lambda _: None)
    for _ in range(2):
        if cpu:
            translator_module._validate_cpu_asr_runtime(str(python))
        else:
            translator_module._get_supported_cli_args(str(python), str(tmp_path))
    assert len(calls) == 2
    assert not (tmp_path / 'logs/engine_probe_cache.json').exists()


def test_probe_cache_is_bounded(probe_runtime, tmp_path):
    for index in range(20):
        translator_module._store_probe(str(index), True)
    cache = json.loads((tmp_path / 'logs/engine_probe_cache.json').read_text(encoding='utf-8'))
    assert len(cache) == 16
    assert '0' not in cache and '19' in cache


@pytest.mark.parametrize('line,level', [
    ('[DEBUG] trace', 'debug'), ('[Assembler] trace', 'debug'),
    ('[FAMILY OPTIMIZER] trace', 'debug'), ('[HY-MT2 OPTIMIZER] trace', 'debug'),
    ('[INFO] ready', 'info'), ('[WARNING] slow', 'warning'),
    ('Traceback (most recent call last):', 'error'), ('unknown', 'error'),
])
def test_engine_stderr_levels(line, level):
    assert translator_module._engine_stderr_level(line) == level


def test_sse_subtitle_log_level(monkeypatch, caplog):
    from backend.api import translation
    async def events():
        yield {'type': 'subtitle', 'data': {'original': '字幕'}}
        yield {'type': 'status', 'data': {'status': 'running'}}
    context = SimpleNamespace(running=True, stream_output=events)
    monkeypatch.setattr(translation, 'get_task', lambda _: context)
    async def scenario():
        response = await translation.stream_subtitles('probe-test')
        return [chunk async for chunk in response.body_iterator]
    with caplog.at_level(logging.DEBUG):
        chunks = asyncio.run(scenario())
    records = [r for r in caplog.records if '[SSE] Sending event' in r.message]
    assert [r.levelno for r in records] == [logging.DEBUG, logging.INFO]
    assert any('字幕' in chunk for chunk in chunks)


def test_cpu_cache_invalidated_by_python_and_engine(probe_runtime):
    python, _, engine, calls, _ = probe_runtime
    translator_module._validate_cpu_asr_runtime(str(python))
    stat = python.stat()
    os.utime(python, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    translator_module._validate_cpu_asr_runtime(str(python))
    assert len(calls) == 2
    (engine / '__init__.py').write_text('VALUE = 333', encoding='utf-8')
    translator_module._validate_cpu_asr_runtime(str(python))
    assert len(calls) == 3


def test_unsuccessful_help_with_flags_is_not_cached(probe_runtime, tmp_path):
    python, _, _, calls, result = probe_runtime
    result.returncode = 1
    for _ in range(2):
        translator_module._get_supported_cli_args(str(python), str(tmp_path))
    assert len(calls) == 2
    assert not (tmp_path / 'logs/engine_probe_cache.json').exists()


def test_cli_refresh_reprobes_and_stores_success(probe_runtime, tmp_path):
    python, _, _, calls, result = probe_runtime
    probe = translator_module._get_supported_cli_args
    assert probe(str(python), str(tmp_path)) == frozenset({'model', 'language'})
    result.stdout = '--model --new_flag'
    assert probe(str(python), str(tmp_path)) == frozenset({'model', 'language'})
    assert len(calls) == 1
    assert probe(str(python), str(tmp_path), refresh=True) == frozenset({'model', 'new_flag'})
    assert len(calls) == 2
    assert probe(str(python), str(tmp_path)) == frozenset({'model', 'new_flag'})
    assert len(calls) == 2


def test_cli_key_tracks_optional_runtime_version(probe_runtime, tmp_path):
    python, version, _, _, _ = probe_runtime
    key = translator_module._probe_key(str(python), str(tmp_path))
    assert key is not None
    version.write_text('{"version": 2}', encoding='utf-8')
    assert translator_module._probe_key(str(python), str(tmp_path)) != key
    version.unlink()
    assert translator_module._probe_key(str(python), str(tmp_path)) is not None
    assert translator_module._probe_key(str(python)) is None


def test_empty_source_directory_uses_site_packages(probe_runtime, tmp_path):
    python, _, engine, _, _ = probe_runtime
    key = translator_module._probe_key(str(python), str(tmp_path))
    (tmp_path / 'stream-translator-gpt').mkdir()
    assert key is not None
    assert translator_module._probe_key(str(python), str(tmp_path)) == key
    (engine / '__init__.py').write_text('VALUE = 444', encoding='utf-8')
    assert translator_module._probe_key(str(python), str(tmp_path)) != key


def test_cpu_key_tracks_removed_sherpa_file(probe_runtime):
    python, _, _, _, _ = probe_runtime
    module = python.parent / 'Lib/site-packages/sherpa_onnx/module.py'
    module.write_text('VALUE = 1', encoding='utf-8')
    key = translator_module._probe_key(str(python))
    assert key is not None
    module.unlink()
    assert translator_module._probe_key(str(python)) != key


@pytest.mark.parametrize('name', ['python311._pth', 'python311.dll'])
def test_cpu_key_tracks_runtime_file_mtime(probe_runtime, name):
    python, _, _, _, _ = probe_runtime
    runtime_file = python.parent / name
    runtime_file.write_bytes(b'runtime')
    key = translator_module._probe_key(str(python))
    assert key is not None
    stat = runtime_file.stat()
    os.utime(runtime_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000000000))
    assert translator_module._probe_key(str(python)) != key


def test_build_command_forwards_audio_preprocess_flags_when_supported(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        '_get_supported_cli_args',
        lambda python_exe, cwd, **kwargs: frozenset({
            'audio_preprocess',
            'disable_audio_agc',
            'audio_agc_max_gain_db',
            'audio_highpass',
        }),
    )
    context = TranslationContext(
        {
            'url': 'https://example.com/live',
            'audio_preprocess': True,
            'disable_audio_agc': True,
            'audio_agc_max_gain_db': 24.0,
            'audio_highpass': True,
        },
        'audio-preprocess-supported',
    )
    command = context._build_command()
    assert '--audio_preprocess' in command
    assert '--disable_audio_agc' in command
    assert '--audio_agc_max_gain_db' in command
    assert command[command.index('--audio_agc_max_gain_db') + 1] == '24.0'
    assert '--audio_highpass' in command


def test_build_command_skips_audio_preprocess_flags_on_old_runtime(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        '_get_supported_cli_args',
        lambda python_exe, cwd, **kwargs: frozenset({'model', 'language'}),
    )
    context = TranslationContext(
        {
            'url': 'https://example.com/live',
            'model': 'turbo',
            'audio_preprocess': True,
            'disable_audio_agc': True,
            'audio_agc_max_gain_db': 24.0,
            'audio_highpass': True,
        },
        'audio-preprocess-old-runtime',
    )
    command = context._build_command()
    assert '--model' in command
    assert '--audio_preprocess' not in command
    assert '--disable_audio_agc' not in command
    assert '--audio_agc_max_gain_db' not in command
    assert '--audio_highpass' not in command
