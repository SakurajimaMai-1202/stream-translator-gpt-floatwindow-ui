import json

from backend.core.config_manager import ConfigManager


def _args(tmp_path, **translation):
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update(translation)
    return manager.to_main_args(config)


def test_context_window_uses_identified_hy_model(tmp_path, monkeypatch, caplog):
    from backend.core import model_identity

    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update(backend='llama', gpt_model='localllm', hy_mt2_context_window=5)
    for served, fallback, expected in (
        ('Hy-MT3-1.8B', 'Hy-MT3-7B', 0),
        ('Hy-MT3-7B', 'Hy-MT3-1.8B', 5),
        ('', 'HY_MT3-1_8B-Q4_K_M.gguf', 0),
    ):
        monkeypatch.setattr(model_identity, 'detect_served_family',
                            lambda *args: ('hy_mt2', served) if served else ('', ''))
        config['llama']['model_path'] = fallback
        caplog.clear()
        with caplog.at_level('INFO'):
            assert manager.to_main_args(config)['hy_mt2_context_window'] == expected
        assert caplog.text.count('context turned off for Hy-MT3 1.8B') == int(expected == 0)
        assert config['translation']['hy_mt2_context_window'] == 5


def test_explicit_hy_family_uses_backend_model(tmp_path, monkeypatch):
    from backend.core import model_identity

    def unexpected_probe(*args, **kwargs):
        raise AssertionError('Explicit family must not probe the server')

    monkeypatch.setattr(model_identity, 'detect_served_family', unexpected_probe)
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    translation = config['translation']
    translation.update(translation_model_family='hy_mt2', gpt_model='localllm', hy_mt2_context_window=3)
    translation['custom_models'] = [
        {'name': 'remote', 'model_name': 'remote-model', 'base_url': 'https://example.invalid/v1'},
    ]
    for backend, filename, expected in (
        ('llama', 'Hy-MT3-1.8B-Q8_0.gguf', 0),
        ('llama', 'Hy-MT3-7B-Q4_K_M.gguf', 3),
        ('custom:remote', 'Hy-MT3-1.8B-Q8_0.gguf', 3),
    ):
        translation['backend'] = backend
        config['llama']['model_path'] = rf'D:\models\{filename}'
        assert manager.to_main_args(config)['hy_mt2_context_window'] == expected


def test_context_window_with_configured_model_name(tmp_path):
    for model, expected in (('tencent/HyMT3-18B', 0), ('Hy-MT3-7B', 5), ('Hy-MT2-1.8B', 5)):
        args = _args(tmp_path, backend='gpt', gpt_model=model, hy_mt2_context_window=5)
        assert args['hy_mt2_context_window'] == expected


def test_default_auto_enabled(tmp_path):
    assert ConfigManager(tmp_path / 'config.yaml').get_config()['translation']['family_optimizer_auto'] is True


def test_auto_off_legacy_hy_enabled(tmp_path):
    args = _args(tmp_path, backend='gpt', gpt_model='HY-MT2-1.8B', family_optimizer_auto=False, hy_mt2_optimizer_enabled=True)
    assert args['hy_mt2_optimizer_enabled'] is True
    assert args['index_translate_optimizer_enabled'] is False


def test_auto_off_legacy_index_enabled(tmp_path):
    args = _args(tmp_path, backend='gpt', gpt_model='Index-Translate-1.0', family_optimizer_auto=False, index_translate_optimizer_enabled=True)
    assert args['index_translate_optimizer_enabled'] is True
    assert args['hy_mt2_optimizer_enabled'] is False


def test_auto_on_generic_ignores_legacy_flags(tmp_path):
    args = _args(tmp_path, backend='gpt', gpt_model='Qwen/Qwen2.5-7B-Instruct', family_optimizer_auto=True, hy_mt2_optimizer_enabled=True)
    assert args['hy_mt2_optimizer_enabled'] is False
    assert args['index_translate_optimizer_enabled'] is False
    assert 'hy_mt2_aliases' not in args


def test_auto_on_backend_none_disables_optimizers(tmp_path):
    args = _args(tmp_path, backend='none', gpt_model='HY-MT2-1.8B', family_optimizer_auto=True)
    assert args['hy_mt2_optimizer_enabled'] is False
    assert args['index_translate_optimizer_enabled'] is False


def test_active_category_supplies_index_aliases(tmp_path):
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update({
        'backend': 'gpt',
        'gpt_model': 'Index-Translate-1.0',
        'translation_glossary_scope': None,
        'hy_mt2_glossary_preset': 'hololive_vtuber',
    })
    config['terminology']['active_categories'] = ['hololive_vtuber']
    args = manager.to_main_args(config)
    aliases = json.loads(args['index_translate_aliases'])
    assert aliases['ホロライブ'] == 'Hololive'


def test_auto_on_hy_enables_only_hy(tmp_path):
    args = _args(tmp_path, backend='gpt', gpt_model='HY-MT2-1.8B', family_optimizer_auto=True,
                 hy_mt2_optimizer_enabled=False, index_translate_optimizer_enabled=False)
    assert args['hy_mt2_optimizer_enabled'] is True
    assert args['index_translate_optimizer_enabled'] is False


def test_auto_on_local_index_model_enables_index_with_aliases(tmp_path, monkeypatch):
    from backend.core import model_identity
    # Server not running: detection falls back to the GGUF selected for llama.cpp.
    monkeypatch.setattr(model_identity, 'detect_served_family', lambda *a, **k: ('', ''))
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update({
        'backend': 'llama', 'gpt_model': 'localllm', 'translation_model_family': 'auto',
        'family_optimizer_auto': True, 'index_translate_optimizer_enabled': False,
        'translation_glossary_scope': 'hololive_vtuber',
    })
    config['llama']['model_path'] = r'D:\models\Index-Translate-9B.i1-IQ4_XS.gguf'
    config['terminology']['active_categories'] = ['hololive_vtuber']
    args = manager.to_main_args(config)
    assert args['translation_model_family'] == 'index_translate'
    assert args['index_translate_optimizer_enabled'] is True
    assert args['hy_mt2_optimizer_enabled'] is False
    assert json.loads(args['index_translate_aliases'])['ホロライブ'] == 'Hololive'


def test_auto_off_legacy_off_disables_both(tmp_path):
    args = _args(tmp_path, backend='gpt', gpt_model='HY-MT2-1.8B', family_optimizer_auto=False,
                 hy_mt2_optimizer_enabled=False, index_translate_optimizer_enabled=False)
    assert args['hy_mt2_optimizer_enabled'] is False
    assert args['index_translate_optimizer_enabled'] is False


def test_auto_never_turns_on_prompt_logging(tmp_path):
    for model in ('HY-MT2-1.8B', 'Index-Translate-1.0'):
        args = _args(tmp_path, backend='gpt', gpt_model=model, family_optimizer_auto=True)
        assert args['hy_mt2_debug'] is False
        assert args['index_translate_debug'] is False
