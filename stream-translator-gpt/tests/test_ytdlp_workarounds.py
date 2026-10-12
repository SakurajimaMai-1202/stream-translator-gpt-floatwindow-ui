from pathlib import Path

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