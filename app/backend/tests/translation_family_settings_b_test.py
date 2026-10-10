import asyncio
import copy
import json
import os

import pytest
from backend.core.config_manager import ConfigManager


def test_index_basic_retains_endpoint_and_independent_settings_after_reload(tmp_path):
    manager = ConfigManager(tmp_path / 'settings.yaml')
    manager.update_section('translation', {
        'backend': 'localllm', 'translation_model_family': 'index_translate',
        'hy_mt2_optimizer_enabled': True, 'hy_mt2_provider': 'lm_studio',
        'hy_mt2_lm_studio_model': 'HY-MT2', 'hy_mt2_context_window': 4,
        'index_translate_optimizer_enabled': False, 'index_translate_context_window': 0,
        'index_translate_provider': 'llama_cpp',
        'index_translate_llama_cpp_url': 'http://127.0.0.1:8081/v1',
        'index_translate_llama_cpp_model': 'Index-Translate-2B-Q4',
    })
    loaded = ConfigManager(tmp_path / 'settings.yaml')
    args = loaded.to_main_args(loaded.get_config())
    assert args['gpt_model'] == 'Index-Translate-2B-Q4'
    assert args['translation_provider'] == 'llama_cpp'
    assert args['index_translate_optimizer_enabled'] is False
    assert args['index_translate_context_window'] == 0
    assert args['hy_mt2_context_window'] == 4


def test_auto_index_is_not_overridden_by_stale_hy_endpoint(tmp_path):
    manager = ConfigManager(tmp_path / 'settings.yaml')
    config = manager.get_config()
    config['translation'].update({
        'translation_model_family': 'auto', 'backend': 'gpt',
        'gpt_model': 'bilibili/Index-Translate-9B',
        'hy_mt2_optimizer_enabled': True, 'hy_mt2_provider': 'lm_studio',
        'hy_mt2_lm_studio_model': 'HY-MT2',
    })
    assert manager.to_main_args(config)['gpt_model'] == 'bilibili/Index-Translate-9B'


def test_index_shared_scope_and_relative_folder(tmp_path):
    manager = ConfigManager(tmp_path / 'settings.yaml')
    config = manager.get_config()
    config['translation'].update({'index_translate_optimizer_enabled': True,
        'translation_model_family': 'index_translate', 'translation_glossary_scope': 'game',
        'index_translate_glossary_folder': 'glossary'})
    config['terminology'].update({'use_terminology_glossary': True, 'glossary_list': [
        {'original': 'すいちゃん', 'translated': '小彗', 'scope': 'game', 'aliases': ['すい']},
        {'original': '包丁', 'translated': '菜刀', 'scope': 'cooking'}]})
    args = manager.to_main_args(config)
    assert json.loads(args['translation_glossary']) == {'すいちゃん': '小彗'}
    assert json.loads(args['index_translate_aliases']) == {'すい': '小彗'}
    assert args['index_translate_glossary_folder'] == str(tmp_path / 'glossary')


def test_preview_stateless_unsaved_config_and_failure_sanitization(tmp_path, monkeypatch):
    from backend.api import translation as api
    from backend.core import llm_translator
    manager = ConfigManager(tmp_path / 'settings.yaml')
    original = copy.deepcopy(manager.get_config())
    environment = dict(os.environ)
    monkeypatch.setattr(api, 'get_config_manager', lambda: manager)
    calls = []
    class FakeClient:
        model_family = 'index_translate'
        def close(self):
            pass
        def translate_preview(self, text, context, diagnostic_glossary=None):
            calls.append((text, context))
            return {'translation': '你好', 'glossary_hits': {}, 'validation': [],
                    'retry_count': 0, 'latency_ms': 12, 'error': 'secret-key'}
    def factory(args, optimized):
        assert args['gpt_model'] == 'Index-Translate-2B'
        return FakeClient()
    monkeypatch.setattr(llm_translator, 'create_family_preview_client', factory)
    request = api.FamilyPreviewRequest(text='こんにちは', config={'translation': {
        'translation_model_family': 'index_translate', 'index_translate_provider': 'lm_studio',
        'index_translate_lm_studio_model': 'Index-Translate-2B'}})
    result = asyncio.run(api.preview_translation(request))
    assert len(calls) == 2
    assert result['basic']['error'] != 'secret-key'
    assert manager.get_config() == original
    assert dict(os.environ) == environment
    request.context = [api.PreviewContext(source='x')] * 6
    with pytest.raises(api.HTTPException) as error:
        asyncio.run(api.preview_translation(request))
    assert error.value.status_code == 400


def test_family_auth_header_is_isolated_and_preview_off_switch_has_alias_data(tmp_path, monkeypatch):
    import httpx
    import openai
    from backend.api import translation as api
    from backend.core.llm_translator import create_family_preview_client
    manager = ConfigManager(tmp_path / 'settings.yaml')
    monkeypatch.setattr(api, 'get_config_manager', lambda: manager)
    request = api.FamilyPreviewRequest(text='すい', config={'translation': {
        'translation_model_family': 'index_translate', 'index_translate_provider': 'lm_studio',
        'index_translate_lm_studio_model': 'Index-Translate-2B',
        'index_translate_lm_studio_api_key': 'test-local-secret',
        'index_translate_optimizer_enabled': False}, 'terminology': {
        'use_terminology_glossary': True, 'glossary_list': [
        {'original': 'すいちゃん', 'translated': '小彗', 'aliases': ['すい']} ]}})
    args = api._resolve_preview_args(request)
    assert json.loads(args['index_translate_aliases']) == {'すい': '小彗'}
    assert args['openai_api_key'] == 'test-local-secret'
    original_openai = openai.OpenAI
    headers = []
    def respond(req):
        headers.append(req.headers.get('Authorization'))
        return httpx.Response(200, json={'choices': [{'message': {'content': '小彗'}}]})
    def factory(**kwargs):
        kwargs['http_client'] = httpx.Client(transport=httpx.MockTransport(respond))
        return original_openai(**kwargs)
    monkeypatch.setattr(openai, 'OpenAI', factory)
    client = create_family_preview_client(args, True)
    try:
        result = client.translate_preview('すい', [])
    finally:
        client.close()
    assert result['translation'] == '小彗'
    assert headers == ['Bearer test-local-secret']
    request.config['translation']['index_translate_lm_studio_api_key'] = ''
    assert api._resolve_preview_args(request)['openai_api_key'] == '114514'


@pytest.mark.parametrize('backend', ['gemini', 'llama'])
def test_external_index_provider_wins_underlying_backend(tmp_path, backend):
    manager = ConfigManager(tmp_path / 'settings.yaml')
    config = manager.get_config()
    config['translation'].update({'backend': backend, 'translation_model_family': 'index',
        'index_translate_provider': 'lm_studio',
        'index_translate_lm_studio_model': 'Index-Translate-2B'})
    args = manager.to_main_args(config)
    assert args['translation_provider'] == 'lm_studio'
    assert args['translation_model_family'] == 'index_translate'
    assert args['gpt_model'] == 'Index-Translate-2B'


@pytest.mark.parametrize('model', ['HY-MT2-1.8B-Q4', 'hymt2-q8'])
def test_auto_core_hy_alias_selects_same_family_endpoint(tmp_path, model):
    manager = ConfigManager(tmp_path / 'settings.yaml')
    config = manager.get_config()
    config['translation'].update({'backend': 'gpt', 'gpt_model': model,
        'hy_mt2_provider': 'lm_studio', 'hy_mt2_lm_studio_model': 'HY-MT2'})
    assert manager.to_main_args(config)['translation_provider'] == 'lm_studio'


def test_config_to_inprocess_client_retains_endpoint_credentials(tmp_path):
    from stream_translator_gpt.pipeline_runner import create_translator
    manager = ConfigManager(tmp_path / 'settings.yaml')
    config = manager.get_config()
    config['translation'].update({'backend': 'gemini', 'translation_model_family': 'index_translate',
        'index_translate_provider': 'lm_studio',
        'index_translate_lm_studio_url': 'http://127.0.0.1:18123/v1',
        'index_translate_lm_studio_model': 'Index-Translate-test',
        'index_translate_lm_studio_api_key': 'local-fixture-key',
        'translation_timeout': 7})
    args = manager.to_main_args(config)
    runner = create_translator(args)
    client = runner.llm_client
    try:
        assert client.provider == 'lm_studio'
        assert client.base_url == 'http://127.0.0.1:18123/v1'
        assert client.api_key == 'local-fixture-key'
        assert client.request_timeout == 7
    finally:
        client.close()
