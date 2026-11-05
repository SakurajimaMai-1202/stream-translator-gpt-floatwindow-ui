from pathlib import Path

import pytest

from stream_translator_gpt import audio_getter

from stream_translator_gpt.audio_getter import _build_ytdlp_command, _resolve_cookie_file


def test_twitter_url_uses_syndication_workaround(tmp_path):
    cookie_file = tmp_path / 'twitter_cookies.txt'
    cookie_file.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')

    cmd = _build_ytdlp_command(
        'https://x.com/i/spaces/1qJVmQDVQEXGB',
        'ba/wa*',
        str(cookie_file),
        'http://127.0.0.1:7890',
        ffmpeg_dir='C:/ffmpeg/bin',
        js_runtime_arg='node:C:/Program Files/nodejs/node.exe',
    )

    assert '--extractor-args' in cmd
    assert 'twitter:api=syndication' in cmd
    assert '--cookies' in cmd
    assert str(cookie_file) in cmd
    assert '--proxy' in cmd


def test_missing_cookie_file_is_ignored_for_any_site(tmp_path):
    missing_cookie_file = tmp_path / 'missing-cookies.txt'

    resolved = _resolve_cookie_file('https://www.youtube.com/watch?v=test', str(missing_cookie_file))

    assert resolved is None


def test_youtube_cookies_are_ignored_for_twitter_url(tmp_path):
    youtube_cookie_file = tmp_path / 'youtubecookies.txt'
    youtube_cookie_file.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')

    resolved = _resolve_cookie_file('https://x.com/i/spaces/1qJVmQDVQEXGB', str(youtube_cookie_file))

    assert resolved is None


def test_non_twitter_url_keeps_regular_cookie_file(tmp_path):
    cookie_file = tmp_path / 'member-cookies.txt'
    cookie_file.write_text('# Netscape HTTP Cookie File\n', encoding='utf-8')

    resolved = _resolve_cookie_file('https://www.youtube.com/watch?v=test', str(cookie_file))

    assert resolved == str(cookie_file)

def test_space_patch_is_pinned_and_bootstraps_are_single_line():
    expected = "for module in ('yt_dlp.extractor.extractors', 'yt_dlp.extractor.twitter'):\n    try:\n        cls = __import__(module, fromlist=['TwitterSpacesIE']).TwitterSpacesIE\n        old = '(?P<id>[0-9a-zA-Z]{13})'\n        if old in cls._VALID_URL:\n            cls._VALID_URL = cls._VALID_URL.replace(old, '(?P<id>[0-9a-zA-Z]{13,})')\n            if '_VALID_URL_RE' in cls.__dict__:\n                delattr(cls, '_VALID_URL_RE')\n    except Exception:\n        pass\n"
    assert audio_getter.YTDLP_SPACE_ID_PATCH == expected
    for bootstrap in (audio_getter.YTDLP_BOOTSTRAP, audio_getter.YTDLP_MODULE_BOOTSTRAP):
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
        # Record the cache so teardown restores or removes it, then clear it.
        monkeypatch.setattr(cls, '_VALID_URL_RE', None, raising=False)
        monkeypatch.delattr(cls, '_VALID_URL_RE')
        cls.suitable('https://x.com/i/spaces/1qJVmQDVQEXGB')
    exec(audio_getter.YTDLP_SPACE_ID_PATCH, {})
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
    # Already-imported submodules would let the patch reach the real classes.
    for name in ('yt_dlp.extractor', 'yt_dlp.extractor.extractors', 'yt_dlp.extractor.twitter'):
        monkeypatch.setitem(sys.modules, name, None)
    monkeypatch.setattr(sys, 'argv', ['-c', '--version'])
    exec(audio_getter.YTDLP_MODULE_BOOTSTRAP, {})
    assert calls == [['yt-dlp', '--version']]
