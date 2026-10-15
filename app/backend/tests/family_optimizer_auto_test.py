import json

from backend.core.config_manager import ConfigManager


def _args(tmp_path, **translation):
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update(translation)
    return manager.to_main_args(config)


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


def test_scope_none_uses_hy_preset_for_index_aliases(tmp_path):
    manager = ConfigManager(tmp_path / 'config.yaml')
    config = manager.get_config()
    config['translation'].update({
        'backend': 'gpt',
        'gpt_model': 'Index-Translate-1.0',
        'translation_glossary_scope': None,
        'hy_mt2_glossary_preset': 'hololive_vtuber',
    })
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
