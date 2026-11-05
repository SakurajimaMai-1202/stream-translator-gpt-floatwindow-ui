import ast
import asyncio
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core import ytdlp_addon as addon


def seed(root, version):
    directory = root / 'addons' / f'yt-dlp-{version}'
    (directory / 'yt_dlp').mkdir(parents=True)
    (directory / 'yt_dlp/__main__.py').write_bytes(b'')
    (directory / '.complete.json').write_text(json.dumps(dict(version=version,
        ejs_version='0.3.0', wheels={}, files={'yt_dlp/__main__.py': 0})), encoding='utf-8')
    pointer = directory.parent / 'yt-dlp-active.json'
    pointer.write_text(json.dumps(dict(version=version, directory=directory.name)), encoding='utf-8')
    return directory


@pytest.fixture
def installation(monkeypatch, tmp_path):
    monkeypatch.setattr(addon, 'get_app_root', lambda: tmp_path)
    monkeypatch.setattr(addon, 'bundled_version', lambda: '2026.10.01')
    monkeypatch.setattr(addon, '_runtime_python', lambda: 'runtime-python')
    old = seed(tmp_path, '2026.10.02')
    payloads, metadata = {}, {}
    for package, version, members in [
        ('yt-dlp', '2026.10.29.232701.dev0', {'yt_dlp/__main__.py': '', 'yt_dlp/__init__.py': ''}),
        ('yt-dlp-ejs', '0.3.0', {'yt_dlp_ejs/__init__.py': ''}),
    ]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            for name, value in members.items():
                archive.writestr(name, value)
        data = buffer.getvalue()
        url = f'https://files.pythonhosted.org/{package}.whl'
        payloads[url] = data
        metadata[package] = {'info': {'requires_dist': ['yt-dlp-ejs==0.3.0; extra == "default"']},
            'urls': [{'filename': f'{package.replace("-", "_")}-{version}-py3-none-any.whl',
                      'url': url, 'size': len(data), 'digests': {'sha256': hashlib.sha256(data).hexdigest()}}]}
    def fetch(url):
        return metadata['yt-dlp-ejs' if '/yt-dlp-ejs/' in url else 'yt-dlp']
    monkeypatch.setattr(addon, '_fetch', fetch)
    class Downloader:
        def __init__(self, progress):
            self.progress = progress
        def download(self, url, path):
            path.write_bytes(payloads[url])
            self.progress(len(payloads[url]), len(payloads[url]))
    monkeypatch.setattr(addon, 'HttpDownloader', Downloader)
    calls = []
    def run(command, timeout):
        calls.append((command, timeout))
        assert command[:3] == ['runtime-python', '-I', '-c']
        # The real command prints a nightly without its wheel's .dev0 suffix.
        return SimpleNamespace(returncode=0, stdout='2026.10.29.232701\n')
    monkeypatch.setattr(addon, '_run', run)
    manager = addon.YtDlpAddonManager()
    manager._latest = '2026.10.29.232701.dev0'
    return SimpleNamespace(manager=manager, old=old, root=tmp_path, metadata=metadata,
                           payloads=payloads, calls=calls)


def test_versions():
    versions = ['2026.10.26.dev0', '2026.10.26', '2026.10.26.220202.dev0',
                '2026.10.26.220202', '2026.10.27']
    assert sorted(versions, key=addon.parse_version) == versions
    assert addon.parse_version('2026.01.02') == addon.parse_version('2026.1.2')
    for value in ['2026.10.26rc1', '2026.10.26.post1', '2026.10.26+local', '../escape', None]:
        assert addon.parse_version(value) is None


def test_pointer_traversal_and_incomplete(installation):
    pointer = installation.old.parent / 'yt-dlp-active.json'
    data = json.loads(pointer.read_text())
    data['directory'] = '../yt-dlp-2026.10.02'
    pointer.write_text(json.dumps(data))
    assert addon.active_addon() is None
    data['directory'] = installation.old.name
    pointer.write_text(json.dumps(data))
    (installation.old / 'yt_dlp/__main__.py').write_bytes(b'changed')
    assert addon.active_addon() is None


def test_newer_bundled_ignores_addon(installation, monkeypatch):
    monkeypatch.setattr(addon, 'bundled_version', lambda: '2026.11.01')
    assert addon.active_addon() is None
    assert addon.ytdlp_command('python') == ['python', '-I', '-X', 'utf8', '-c', addon.MODULE_BOOTSTRAP]
    monkeypatch.setattr(addon, 'bundled_version', lambda: None)
    assert addon.active_addon() == installation.old


@pytest.mark.parametrize('failure', ['digest', 'missing_digest', 'host', 'pin', 'unsafe', 'smoke', 'import'])
def test_failure_preserves_pointer(installation, monkeypatch, failure):
    f = installation
    wheel = f.metadata['yt-dlp']['urls'][0]
    if failure == 'digest':
        wheel['digests']['sha256'] = '0' * 64
    elif failure == 'missing_digest':
        wheel['digests'] = {}
    elif failure == 'host':
        wheel['url'] = 'https://example.com/file.whl'
    elif failure == 'pin':
        f.metadata['yt-dlp']['info']['requires_dist'] = ['yt-dlp-ejs>=0.3.0; extra == "default"']
    elif failure == 'unsafe':
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('../escape', 'unsafe')
        data = buffer.getvalue()
        f.payloads[wheel['url']] = data
        wheel.update(size=len(data), digests={'sha256': hashlib.sha256(data).hexdigest()})
    elif failure in {'smoke', 'import'}:
        monkeypatch.setattr(addon, '_run', lambda command, timeout: SimpleNamespace(
            returncode=1 if failure == 'smoke' or '--version' not in command else 0,
            stdout=f.manager._latest))
    pointer = f.old.parent / 'yt-dlp-active.json'
    before = pointer.read_bytes()
    f.manager.install()
    assert f.manager.status()['state'] == 'error'
    assert '已保留目前版本' in f.manager.status()['error']
    assert pointer.read_bytes() == before
    assert addon.active_addon() == f.old
    assert not list(f.old.parent.glob('.yt-dlp-*'))


def test_success_retains_previous_until_next_install_and_restore(installation):
    f = installation
    f.manager.install()
    assert f.manager.status()['state'] == 'idle'
    current = addon.active_addon()
    assert current != f.old and f.old.exists()
    assert len(f.calls) == 2 and all(timeout == 60 for _, timeout in f.calls)
    manifest = json.loads((current / '.complete.json').read_text())
    assert len(manifest['wheels']) == 2 and manifest['ejs_version'] == '0.3.0'
    env = {'STREAM_TRANSLATOR_YTDLP_ADDON': 'stale'}
    addon.apply_ytdlp_addon_environment(env)
    assert env['STREAM_TRANSLATOR_YTDLP_ADDON'] == str(current)
    f.manager._latest = '2026.10.30'
    f.manager.install()  # Fake smoke version differs; current pointer still survives.
    assert not f.old.exists() and addon.active_addon() == current
    assert f.manager.restore_bundled()['active_version'] == '2026.10.01'
    assert not (current.parent / 'yt-dlp-active.json').exists()
    addon.apply_ytdlp_addon_environment(env)
    assert 'STREAM_TRANSLATOR_YTDLP_ADDON' not in env


def test_damaged_addon_of_same_version_can_be_reinstalled(installation):
    f = installation
    f.manager.install()
    current = addon.active_addon()
    (current / 'yt_dlp' / '__main__.py').unlink()
    assert addon.active_addon() is None
    f.manager.install()
    assert f.manager.status()['state'] == 'idle' and addon.active_addon() == current


def test_check_nightly_and_get_never_fetches(installation, monkeypatch):
    calls = []
    def fetch(url):
        calls.append(url)
        return {'releases': {'2026.10.26': [{}], '2026.10.26.220202.dev0': [{}],
                            '2026.10.27': [{'yanked': True}], '2026.10.28rc1': [{}]}}
    monkeypatch.setattr(addon, '_fetch', fetch)
    installation.manager.status()
    assert not calls
    assert installation.manager.check()['latest_version'] == '2026.10.26.220202.dev0'


def test_begin_busy_and_no_update(installation, monkeypatch):
    manager = installation.manager
    monkeypatch.setattr(addon.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))
    assert manager.begin()['state'] == 'downloading'
    for action in (manager.begin, manager.restore_bundled, manager.check):
        with pytest.raises(RuntimeError):
            action()
    manager._set('idle')
    manager._latest = '2026.01.01'
    with pytest.raises(RuntimeError):
        manager.begin()


def test_bootstrap_executes_and_forwards_arguments(tmp_path):
    package = tmp_path / 'yt_dlp'
    package.mkdir()
    (package / '__init__.py').write_text('import json, sys\ndef main(): print(json.dumps(sys.argv))\n', encoding='utf-8')
    result = subprocess.run([sys.executable, '-I', '-c', addon.BOOTSTRAP, str(tmp_path),
                             '--version', 'argument with spaces'], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == ['yt-dlp', '--version', 'argument with spaces']


def test_bootstrap_matches_engine():
    def assignments(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        return {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}

    engine = assignments(Path(__file__).resolve().parents[3]
                         / 'stream-translator-gpt/stream_translator_gpt/audio_getter.py')
    backend = assignments(Path(addon.__file__))
    assert ast.literal_eval(engine['YTDLP_SPACE_ID_PATCH']) == addon.YTDLP_SPACE_ID_PATCH
    for engine_name, backend_name in (('YTDLP_BOOTSTRAP', 'BOOTSTRAP'),
                                      ('YTDLP_MODULE_BOOTSTRAP', 'MODULE_BOOTSTRAP')):
        engine_value = ast.dump(engine[engine_name]).replace('YTDLP_SPACE_ID_PATCH', 'PATCH')
        backend_value = ast.dump(backend[backend_name]).replace('YTDLP_SPACE_ID_PATCH', 'PATCH')
        assert engine_value == backend_value


def test_api_running_conflicts(monkeypatch):
    from backend.api import runtime
    from backend.core import translator
    monkeypatch.setattr(translator, 'active_translations', {'task': SimpleNamespace(running=True)})
    for action in (runtime.update_ytdlp, runtime.restore_ytdlp):
        with pytest.raises(runtime.HTTPException) as exc:
            asyncio.run(action())
        assert exc.value.status_code == 409


def test_bundled_version_cached_runtime_only(monkeypatch):
    monkeypatch.setattr(addon, '_bundled', None); monkeypatch.setattr(addon, '_bundled_retry_at', 0.0)
    monkeypatch.setattr(addon, '_runtime_python', lambda: 'runtime-python')
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert command[:3] == ['runtime-python', '-I', '-c']
        assert kwargs['timeout'] == 20
        return SimpleNamespace(returncode=0, stdout='2026.10.26\n')
    monkeypatch.setattr(addon, 'run_external', run)
    assert addon.bundled_version() == addon.bundled_version() == '2026.10.26'
    assert len(calls) == 1


def test_bundled_failure_retries_later_and_frozen_gui_never_spawned(monkeypatch, tmp_path):
    from backend.core import cookie_manager
    monkeypatch.setattr(addon, '_bundled', None); monkeypatch.setattr(addon, '_bundled_retry_at', 0.0)
    monkeypatch.setattr(addon.sys, 'frozen', True, raising=False)
    executable = tmp_path / 'Stream Translator.exe'
    monkeypatch.setattr(addon.sys, 'executable', str(executable))
    monkeypatch.setattr(cookie_manager, '_resolve_runtime_python', lambda: executable)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError('must never spawn the GUI')
    monkeypatch.setattr(addon, 'run_external', forbidden)
    assert addon.bundled_version() is None
    assert addon._bundled is None and addon._bundled_retry_at > 0
    assert not calls


def test_api_status_is_local_and_runtime_errors_are_conflicts(installation, monkeypatch):
    from backend.api import runtime
    from backend.core import translator
    monkeypatch.setattr(runtime, 'ytdlp_addon_manager', installation.manager)
    monkeypatch.setattr(translator, 'active_translations', {})
    def forbidden(url):
        raise AssertionError('status must not fetch PyPI')
    monkeypatch.setattr(addon, '_fetch', forbidden)
    assert asyncio.run(runtime.get_ytdlp_status())['data']['active_version'] == '2026.10.02'
    installation.manager._set('installing')
    for action in (runtime.update_ytdlp, runtime.restore_ytdlp):
        with pytest.raises(runtime.HTTPException) as exc:
            asyncio.run(action())
        assert exc.value.status_code == 409


def test_space_patch_is_pinned_and_bootstraps_are_single_line():
    expected = "for module in ('yt_dlp.extractor.extractors', 'yt_dlp.extractor.twitter'):\n    try:\n        cls = __import__(module, fromlist=['TwitterSpacesIE']).TwitterSpacesIE\n        old = '(?P<id>[0-9a-zA-Z]{13})'\n        if old in cls._VALID_URL:\n            cls._VALID_URL = cls._VALID_URL.replace(old, '(?P<id>[0-9a-zA-Z]{13,})')\n            if '_VALID_URL_RE' in cls.__dict__:\n                delattr(cls, '_VALID_URL_RE')\n    except Exception:\n        pass\n"
    assert addon.YTDLP_SPACE_ID_PATCH == expected
    for bootstrap in (addon.BOOTSTRAP, addon.MODULE_BOOTSTRAP):
        assert '\n' not in bootstrap and '\r' not in bootstrap
        assert 'exec(' + repr(expected) + ')' in bootstrap
        compile(bootstrap, '<bootstrap>', 'exec')


def test_space_patch_matches_installed_lazy_and_real_extractors(monkeypatch):
    pytest.importorskip('yt_dlp')
    from yt_dlp.extractor.extractors import TwitterSpacesIE as lazy
    from yt_dlp.extractor.twitter import TwitterSpacesIE as real

    for cls in dict.fromkeys((lazy, real)):
        # Prime the old compiled pattern to verify cache invalidation as well.
        monkeypatch.setattr(cls, '_VALID_URL', cls._VALID_URL)
        monkeypatch.setattr(cls, '_VALID_URL_RE', cls.__dict__.get('_VALID_URL_RE'), raising=False)
        delattr(cls, '_VALID_URL_RE')
        cls.suitable('https://x.com/i/spaces/1qJVmQDVQEXGB')
    exec(addon.YTDLP_SPACE_ID_PATCH, {})
    for cls in (lazy, real):
        for space_id in ('1kEvJlqpyyePkq', '1qJVmQDVQEXGB'):
            url = 'https://x.com/i/spaces/' + space_id
            assert cls.suitable(url)
            assert cls._match_id(url) == space_id


def test_module_bootstrap_runs_main_when_patch_import_fails(monkeypatch):
    import sys
    from types import ModuleType
    fake = ModuleType('yt_dlp')
    calls = []
    fake.main = lambda: calls.append(list(sys.argv))
    monkeypatch.setitem(sys.modules, 'yt_dlp', fake)
    monkeypatch.setattr(sys, 'argv', ['-c', '--version'])
    exec(addon.MODULE_BOOTSTRAP, {})
    assert calls == [['yt-dlp', '--version']]
