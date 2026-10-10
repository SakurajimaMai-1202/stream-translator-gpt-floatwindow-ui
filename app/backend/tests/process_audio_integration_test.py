import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from backend.core.config_manager import ConfigManager
from backend.core import source_checks, translator
from backend.models.translation import AudioSource, StartTranslationRequest


async def inline_thread_call(function, *args, **kwargs):
    return function(*args, **kwargs)


def run_inline(coroutine):
    """Unit-test route branches without network/event-loop platform dependencies."""
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    finally:
        coroutine.close()
    raise AssertionError('Unexpected asynchronous suspension')


def configuration(source='process_audio'):
    config = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
    config['input'].update(audio_source=source, url='https://old.example/live', process_id=123,
                           process_start_time='134038470994534567')
    return config


def test_process_source_is_distinct_and_preserves_filetime_precision():
    request = StartTranslationRequest(audio_source='process_audio', process_id=123,
                                     process_start_time='134038470994534567')
    assert request.audio_source == AudioSource.PROCESS_AUDIO
    manager = ConfigManager.__new__(ConfigManager)
    args = manager.to_main_args(configuration())
    assert args['url'] == 'process_audio'
    assert args['process_start_time'] == '134038470994534567'
    assert args['process_id'] == 123
    assert args['loopback'] is False
    for source in ('url', 'file', 'microphone', 'system_audio'):
        args = manager.to_main_args(configuration(source))
        assert args['process_id'] is None
        assert args['process_start_time'] == ''


@pytest.mark.parametrize('supported', [None, frozenset({'device_index'}), frozenset({'process_id'})])
def test_old_runtime_never_silently_drops_process_target(monkeypatch, supported):
    monkeypatch.setattr(translator, '_resolve_profile_python', lambda *args: None)
    def help_args(*args):
        return supported
    help_args.cache_clear = lambda: None
    monkeypatch.setattr(translator, '_get_supported_cli_args', help_args)
    context = translator.TranslationContext({'url': 'process_audio', 'process_id': 123,
                                            'process_start_time': '134038470994534567'}, 'test')
    with pytest.raises(RuntimeError, match='不支援指定程式收音'):
        context._build_command()


def test_supported_runtime_passes_complete_target(monkeypatch):
    monkeypatch.setattr(translator, '_resolve_profile_python', lambda *args: None)
    monkeypatch.setattr(translator, '_get_supported_cli_args', lambda *args: frozenset({'process_id', 'process_start_time'}))
    command = translator.TranslationContext({'url': 'process_audio', 'process_id': 123,
                                            'process_start_time': '134038470994534567'}, 'test')._build_command()
    assert command[-1] == 'process_audio'
    assert command[command.index('--process_id') + 1] == '123'
    assert command[command.index('--process_start_time') + 1] == '134038470994534567'


@pytest.mark.parametrize('received,status', [(False, 'unknown'), (True, 'ready')])
def test_probe_distinguishes_silence_from_audio(monkeypatch, received, status):
    monkeypatch.setattr('backend.core.process_audio.validate_process_target', lambda *args: {})
    monkeypatch.setattr(source_checks, '_process_audio_probe_command', lambda *args: ['probe'])
    monkeypatch.setattr(source_checks, 'run_external', lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({'received_audio': received, 'peak': 0.02}), stderr=''))
    result = source_checks.check_process_audio(123, '134038470994534567')
    assert result.status == status
    assert result.details['received_audio'] is received


def test_dead_or_reused_target_fails_before_capture(monkeypatch):
    def stale(*args):
        raise ValueError('PID 已重用')
    monkeypatch.setattr('backend.core.process_audio.validate_process_target', stale)
    monkeypatch.setattr(source_checks, 'run_external', lambda *args, **kwargs: pytest.fail('must not capture'))
    result = source_checks.check_process_audio(123, '134038470994534567')
    assert result.status == 'error'
    assert result.stage == 'target'
    assert result.message == 'PID 已重用'


def test_probe_uses_selected_runtime_source_prefix(monkeypatch):
    class Manager:
        def get_config(self):
            return configuration()
        def to_main_args(self, config):
            return config['input']
    monkeypatch.setattr('backend.api.config.get_config_manager', lambda: Manager())
    monkeypatch.setattr(translator.TranslationContext, '_build_command', lambda self: [
        'selected-python.exe', '-c', "import runpy,sys;sys.path.insert(0,'source');runpy.run_module('stream_translator_gpt',run_name='__main__')",
        '--model', 'large', 'process_audio'])
    command = source_checks._process_audio_probe_command(123, '134038470994534567', 0.5)
    assert command[0] == 'selected-python.exe'
    assert 'stream_translator_gpt.process_audio_capture' in command[2]
    assert '--model' not in command
    assert command[-2:] == ['--duration', '0.5']


def test_api_preserves_target_validation_error_and_does_not_start_model(monkeypatch):
    from backend.api import translation as api
    class Manager:
        def get_config(self):
            return configuration()
        def to_main_args(self, config):
            return {'url': 'process_audio'}
    def stale(*args):
        raise ValueError('目標程式已關閉')
    monkeypatch.setattr(api, 'get_config_manager', lambda: Manager())
    monkeypatch.setattr(api, 'validate_process_target', stale)
    monkeypatch.setattr(api.asyncio, 'to_thread', inline_thread_call)
    monkeypatch.setattr(api, 'create_task', lambda *args: pytest.fail('must not start model'))
    request = StartTranslationRequest(audio_source='process_audio', process_id=123,
                                     process_start_time='134038470994534567')
    with pytest.raises(HTTPException) as exc:
        run_inline(api.start_translation(request, SimpleNamespace(headers={})))
    assert exc.value.status_code == 400
    assert exc.value.detail == '目標程式已關閉'


def test_other_source_cannot_start_while_process_task_runs(monkeypatch):
    from backend.api import translation as api
    class Manager:
        def get_config(self):
            return configuration('system_audio')
        def to_main_args(self, config):
            return {'url': 'loopback'}
    monkeypatch.setattr(api, 'get_config_manager', lambda: Manager())
    monkeypatch.setattr(api, 'active_translations', {'existing': SimpleNamespace(running=True, config={'url': 'process_audio'})})
    monkeypatch.setattr(api, 'create_task', lambda *args: pytest.fail('must not start second model'))
    with pytest.raises(HTTPException) as exc:
        run_inline(api.start_translation(StartTranslationRequest(audio_source='system_audio'), SimpleNamespace(headers={})))
    assert exc.value.status_code == 409


def test_stop_before_background_task_runs_never_starts_capture(monkeypatch):
    scheduled = []
    monkeypatch.setattr(translator.asyncio, 'get_running_loop', lambda: object())
    monkeypatch.setattr(translator.asyncio, 'create_task', scheduled.append)
    monkeypatch.setattr(translator, 'persistent_process', None)
    context = translator.TranslationContext({'url': 'process_audio'}, 'stop-before-launch')
    monkeypatch.setattr(context, '_build_command', lambda: pytest.fail('stopped task must not launch capture'))
    run_inline(context.start())
    assert context.running
    run_inline(context.stop())
    assert not context.running
    assert len(scheduled) == 1
    run_inline(scheduled[0])
    assert context.process is None
