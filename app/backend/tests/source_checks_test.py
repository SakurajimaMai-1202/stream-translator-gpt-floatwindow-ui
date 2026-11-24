import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core import source_checks
from backend.core.ytdlp_addon import MODULE_BOOTSTRAP


def test_file_check_distinguishes_missing_file(tmp_path):
    result = source_checks.check_file(str(tmp_path / "missing.mp4"))
    assert result.status == "error"
    assert result.stage == "file_open"
    assert result.trace_id


@pytest.mark.parametrize("returncode,stdout,stderr", [
    (1, None, "彗醬測試すいせい.mp4: Invalid data found when processing input"),
    (1, None, None),
    (0, "invalid JSON", None),
    (0, None, None),
])
def test_file_check_reports_decode_error(monkeypatch, tmp_path, returncode, stdout, stderr):
    media = tmp_path / "彗醬測試すいせい.mp4"
    media.touch()
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: name)

    def run(command, **kwargs):
        assert command == [
            "ffprobe", "-v", "error", "-show_entries", "stream=index,codec_type,codec_name",
            "-of", "json", str(media),
        ]
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(source_checks.subprocess, "run", run)
    result = source_checks.check_file(str(media))
    assert (result.status, result.stage, result.message) == ("error", "decode", "影音格式無法解析")
    assert result.details["technical_detail"] == (stderr or "")


def test_file_check_reports_missing_audio(monkeypatch, tmp_path):
    media = tmp_path / "silent.mp4"
    media.write_bytes(b"stub")
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: "ffprobe")
    monkeypatch.setattr(source_checks.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({"streams": [{"codec_type": "video"}]}), stderr=""
    ))
    result = source_checks.check_file(str(media))
    assert result.status == "error"
    assert result.stage == "audio_track"


def test_file_check_reports_decodable_audio(monkeypatch, tmp_path):
    media = tmp_path / "sample.mp4"
    media.write_bytes(b"stub")
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: "ffprobe")
    monkeypatch.setattr(source_checks.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps({"streams": [{"codec_type": "audio", "codec_name": "aac"}]}), stderr=""
    ))
    result = source_checks.check_file(str(media))
    assert result.status == "ready"
    assert result.details["audio_streams"][0]["codec_name"] == "aac"


def test_url_check_rejects_invalid_url():
    result = source_checks.check_url("not a url")
    assert result.status == "error"
    assert result.stage == "url_format"


def test_url_check_reports_audio_stream(monkeypatch):
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: "yt-dlp")
    monkeypatch.setattr(source_checks, "run_external", lambda *args, **kwargs: SimpleNamespace(
        returncode=0,
        stdout=json.dumps({"title": "Live", "live_status": "is_live", "formats": [
            {"acodec": "none"}, {"acodec": "opus"},
        ]}),
        stderr="",
    ))
    result = source_checks.check_url("https://example.com/live")
    assert result.status == "ready"
    assert result.stage == "stream"
    assert result.details["audio_format_count"] == 1


def test_missing_resolver_is_unknown_not_ready(monkeypatch):
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: None)
    def missing_runtime():
        raise RuntimeError("missing")
    monkeypatch.setattr(source_checks, "_resolve_runtime_python", missing_runtime)
    result = source_checks.check_url("https://example.com/live")
    assert result.status == "unknown"
    assert result.stage == "resolver"


def test_url_precheck_prefers_bundled_runtime_and_node_over_stale_path(monkeypatch, tmp_path):
    runtime = tmp_path / "_runtime" / "python.exe"
    runtime.parent.mkdir()
    runtime.touch()
    node = tmp_path / "_js_runtime" / "node.exe"
    node.parent.mkdir()
    node.touch()
    monkeypatch.setattr(source_checks, "_resolve_runtime_python", lambda: runtime)
    monkeypatch.setattr(source_checks.sys, "frozen", True, raising=False)
    monkeypatch.setattr(source_checks.sys, "executable", str(tmp_path / "Stream Translator.exe"))
    monkeypatch.setattr(source_checks.shutil, "which", lambda name: str(tmp_path / "stale" / name))
    observed = {}
    def run(command, **kwargs):
        observed.update(command=command, options=kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"formats": [{"acodec": "opus"}]}), stderr="")
    monkeypatch.setattr(source_checks, "run_external", run)
    result = source_checks.check_url("https://example.com/live")
    assert result.status == "ready"
    assert observed["command"][:8] == [str(runtime), "-I", "-X", "utf8", "-c", MODULE_BOOTSTRAP, "--js-runtimes", f"node:{node}"]
    assert observed["options"]["timeout"] == 20
    assert observed["options"]["encoding"] == "utf-8" and observed["options"]["errors"] == "replace"


@pytest.mark.parametrize("host,is_twitter", [
    ("x.com", True),
    ("mobile.twitter.com", True),
    ("media.x.com", True),
    ("youtube.com", False),
    ("x.com.example.org", False),
    ("not-twitter.com", False),
])
def test_url_probe_flags(monkeypatch, tmp_path, host, is_twitter):
    runtime = tmp_path / "python.exe"
    monkeypatch.setattr(source_checks, "_resolve_runtime_python", lambda: runtime)
    url = f"https://{host}/live"

    def run(command, **kwargs):
        flags = ["--no-playlist", "--skip-download", "--dump-single-json"]
        if is_twitter:
            flags.extend(["--extractor-args", "twitter:api=syndication"])
        assert command[:5] == [str(runtime), "-I", "-X", "utf8", "-c"]
        assert command[-len(flags) - 1:] == flags + [url]
        assert ("--extractor-args" in command) == is_twitter
        return SimpleNamespace(returncode=0, stdout='{"formats": [{"acodec": "opus"}]}')

    monkeypatch.setattr(source_checks, "run_external", run)
    assert source_checks.check_url(url).status == "ready"


def test_url_command_addon_keeps_node_arguments(monkeypatch, tmp_path):
    runtime = tmp_path / '_runtime/python.exe'
    runtime.parent.mkdir()
    runtime.touch()
    node = tmp_path / '_js_runtime/node.exe'
    node.parent.mkdir()
    node.touch()
    monkeypatch.setattr(source_checks, '_resolve_runtime_python', lambda: runtime)
    prefix = [str(runtime), '-I', '-c', 'bootstrap', 'addon']
    monkeypatch.setattr(source_checks, 'ytdlp_command', lambda python: prefix.copy())
    assert source_checks._resolve_url_command() == prefix + ['--js-runtimes', f'node:{node}']


@pytest.mark.parametrize('stderr,message,recovery', [
    ('ERROR: Twitter Space not found', '找不到這個 X Space（網址錯誤、已刪除、尚未開始，或需要登入 Cookie）',
     '確認網址完整；若 Space 尚未開始請等開播後再試，需要登入時請設定 X 的 Cookie。'),
    ('ERROR: Twitter Space ended and replay is disabled', 'X Space 已結束，且主持人沒有開放重播',
     '這場 Space 已無法收聽；請改用正在進行或有開放重播的 Space。'),
])
def test_space_resolve_error_has_specific_reason(monkeypatch, stderr, message, recovery):
    monkeypatch.setattr(source_checks, '_resolve_url_command', lambda: ['fake'])
    monkeypatch.setattr(source_checks, 'run_external', lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout='', stderr=stderr))
    result = source_checks.check_url('https://x.com/i/spaces/1kEvJlqpyyePkq')
    assert (result.stage, result.status) == ('resolve', 'error')
    assert result.message == message
    assert result.recovery == recovery
    assert result.details['technical_detail'] == stderr


def test_url_failure_detail_hides_query_strings(monkeypatch):
    url = "https://cdn.example.com/a.m3u8"
    padding = "." * 1150
    stderr = f"ERROR: HTTP Error 403 for {url}?token={'secret' * 300}&sig=abc\n{padding}"
    monkeypatch.setattr(source_checks, '_resolve_url_command', lambda: ['fake'])
    monkeypatch.setattr(source_checks, 'run_external', lambda *a, **kw: SimpleNamespace(
        returncode=1, stdout='', stderr=stderr))
    result = source_checks.check_url('https://example.com/live')
    detail = result.details['technical_detail']
    assert detail == f"ERROR: HTTP Error 403 for {url}?…\n{padding}"[-1200:]
