import json
from pathlib import Path
from types import SimpleNamespace

from backend.core import source_checks


def test_file_check_distinguishes_missing_file(tmp_path):
    result = source_checks.check_file(str(tmp_path / "missing.mp4"))
    assert result.status == "error"
    assert result.stage == "file_open"
    assert result.trace_id


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
    monkeypatch.setattr(source_checks.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
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
    result = source_checks.check_url("https://example.com/live")
    assert result.status == "unknown"
    assert result.stage == "resolver"
