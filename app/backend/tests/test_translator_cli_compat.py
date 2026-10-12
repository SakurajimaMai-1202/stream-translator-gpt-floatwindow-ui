import backend.core.translator as translator_module
from backend.core.translator import TranslationContext


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
