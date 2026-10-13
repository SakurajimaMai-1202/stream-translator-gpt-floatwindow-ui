import backend.core.translator as translator_module
from backend.core.translator import TranslationContext
import asyncio
import logging
import threading


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
        lambda python_exe, cwd: frozenset({
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


def test_build_command_keeps_args_when_runtime_capability_unknown(monkeypatch):
    monkeypatch.setattr(translator_module, '_get_supported_cli_args', lambda python_exe, cwd: None)

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
