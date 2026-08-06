from pathlib import Path

from stream_translator_gpt import audio_getter


def test_resolve_js_runtime_finds_standard_windows_node(monkeypatch, tmp_path):
    runtime_python = tmp_path / "runtime-without-node" / "python.exe"
    runtime_python.parent.mkdir()
    runtime_python.write_bytes(b"")
    node = tmp_path / "nodejs" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"")
    monkeypatch.setattr(audio_getter.sys, "executable", str(runtime_python))
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setattr(audio_getter.shutil, "which", lambda _name: None)
    audio_getter._resolve_js_runtime_arg.cache_clear()

    assert audio_getter._resolve_js_runtime_arg() == f"node:{node.resolve()}"


def test_ytdlp_command_enables_runtime_and_ejs(monkeypatch):
    monkeypatch.setattr(audio_getter, "_resolve_ytdlp_command", lambda: ["yt-dlp"])
    command = audio_getter._build_ytdlp_command(
        "https://www.youtube.com/watch?v=test",
        "ba",
        "",
        "",
        js_runtime_arg=r"node:C:\Program Files\nodejs\node.exe",
    )

    assert command[command.index("--js-runtimes") + 1] == r"node:C:\Program Files\nodejs\node.exe"
    assert command[command.index("--remote-components") + 1] == "ejs:github"


def test_resolve_js_runtime_finds_node_bundled_beside_runtime(monkeypatch, tmp_path):
    runtime_python = tmp_path / "_runtime" / "python.exe"
    runtime_python.parent.mkdir()
    runtime_python.write_bytes(b"")
    node = tmp_path / "_js_runtime" / "node.exe"
    node.parent.mkdir()
    node.write_bytes(b"")
    monkeypatch.setattr(audio_getter.sys, "executable", str(runtime_python))
    monkeypatch.setattr(audio_getter.shutil, "which", lambda _name: None)
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "missing"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    audio_getter._resolve_js_runtime_arg.cache_clear()

    assert audio_getter._resolve_js_runtime_arg() == f"node:{node.resolve()}"
