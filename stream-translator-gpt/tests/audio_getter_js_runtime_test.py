from pathlib import Path
import queue
import threading

import numpy as np

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AUDIO_STREAM_GAP


def test_ytdlp_command_prefers_current_python_module_over_old_path_executable(monkeypatch, tmp_path):
    runtime_python = tmp_path / "_runtime" / "python.exe"
    runtime_python.parent.mkdir()
    runtime_python.write_bytes(b"")
    old_global_ytdlp = tmp_path / "global" / "yt-dlp.exe"
    old_global_ytdlp.parent.mkdir()
    old_global_ytdlp.write_bytes(b"")

    monkeypatch.setattr(audio_getter.sys, "executable", str(runtime_python))
    monkeypatch.setattr(audio_getter.importlib.util, "find_spec", lambda name: object() if name == "yt_dlp" else None)
    monkeypatch.setattr(audio_getter.shutil, "which", lambda _name: str(old_global_ytdlp))

    assert audio_getter._resolve_ytdlp_command() == [
        str(runtime_python),
        "-c",
        audio_getter.YTDLP_MODULE_BOOTSTRAP,
    ]


def test_ytdlp_command_uses_runtime_scripts_before_system_path(monkeypatch, tmp_path):
    runtime_python = tmp_path / "_runtime" / "python.exe"
    runtime_python.parent.mkdir()
    runtime_python.write_bytes(b"")
    runtime_ytdlp = runtime_python.parent / "Scripts" / "yt-dlp.exe"
    runtime_ytdlp.parent.mkdir()
    runtime_ytdlp.write_bytes(b"")

    monkeypatch.setattr(audio_getter.sys, "executable", str(runtime_python))
    monkeypatch.setattr(audio_getter.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(audio_getter.shutil, "which", lambda _name: str(tmp_path / "global" / "yt-dlp.exe"))

    assert audio_getter._resolve_ytdlp_command() == [str(runtime_ytdlp)]


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
    assert command[command.index("--fragment-retries") + 1] == "infinite"
    assert command[command.index("--retry-sleep") + 1] == "fragment:1"
    # ffmpeg errors must stay visible despite -q (upstream 17017d2).
    assert command[command.index("--downloader-args") + 1] == "ffmpeg:-loglevel error"


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


def test_resolve_js_runtime_prefers_bundled_node_over_old_path_node(monkeypatch, tmp_path):
    runtime_python = tmp_path / "_runtime" / "python.exe"
    runtime_python.parent.mkdir()
    runtime_python.write_bytes(b"")
    bundled_node = tmp_path / "_js_runtime" / "node.exe"
    bundled_node.parent.mkdir()
    bundled_node.write_bytes(b"")
    old_node = tmp_path / "old-global" / "node.exe"
    old_node.parent.mkdir()
    old_node.write_bytes(b"")
    monkeypatch.setattr(audio_getter.sys, "executable", str(runtime_python))
    monkeypatch.setattr(audio_getter.shutil, "which", lambda _name: str(old_node))
    audio_getter._resolve_js_runtime_arg.cache_clear()

    assert audio_getter._resolve_js_runtime_arg() == f"node:{bundled_node.resolve()}"


def test_youtube_stream_reconnects_after_audio_stall(monkeypatch):
    release_stalled_read = threading.Event()

    class Stdout:
        def __init__(self, chunks=None, block=False):
            self.chunks = list(chunks or [])
            self.block = block

        def read(self, _size):
            if self.block:
                release_stalled_read.wait(timeout=1)
                return b""
            return self.chunks.pop(0) if self.chunks else b""

    class Process:
        def __init__(self, stdout):
            self.stdout = stdout
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0
            release_stalled_read.set()

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    getter = audio_getter.StreamAudioGetter(
        "https://www.youtube.com/watch?v=live", "ba", "", ""
    )
    getter.STREAM_READ_TIMEOUT_SECONDS = 0.02
    getter.YOUTUBE_RECONNECT_DELAY_SECONDS = 0
    pcm = np.zeros(audio_getter.SAMPLES_PER_FRAME, dtype=np.float32).tobytes()
    opens = []

    def fake_open(*_args):
        opens.append(True)
        if len(opens) == 1:
            return Process(Stdout(block=True)), Process(Stdout())
        return Process(Stdout([pcm])), Process(Stdout())

    monkeypatch.setattr(audio_getter, "_open_stream", fake_open)
    statuses = iter(['live', 'live', 'ended'])
    monkeypatch.setattr(getter, '_source_status', lambda: next(statuses))
    output = queue.SimpleQueue()

    getter.loop(output)

    assert len(opens) == 2
    assert output.get() is AUDIO_STREAM_GAP
    assert output.get().shape == (audio_getter.SAMPLES_PER_FRAME,)
    # S6: EOF flushes the tail immediately, before the end-of-stream sentinel.
    assert output.get() is AUDIO_STREAM_GAP
    assert output.get() is None


def test_ytdlp_addon_command_and_unset_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(audio_getter.importlib.util, 'find_spec', lambda name: object())
    monkeypatch.delenv('STREAM_TRANSLATOR_YTDLP_ADDON', raising=False)
    assert audio_getter._resolve_ytdlp_command() == [audio_getter.sys.executable, '-c', audio_getter.YTDLP_MODULE_BOOTSTRAP]
    monkeypatch.setenv('STREAM_TRANSLATOR_YTDLP_ADDON', str(tmp_path))
    assert audio_getter._resolve_ytdlp_command() == [audio_getter.sys.executable, '-c', audio_getter.YTDLP_MODULE_BOOTSTRAP]
    (tmp_path / 'yt_dlp').mkdir()
    (tmp_path / 'yt_dlp/__main__.py').touch()
    assert audio_getter._resolve_ytdlp_command() == [
        audio_getter.sys.executable, '-I', '-X', 'utf8', '-c', audio_getter.YTDLP_BOOTSTRAP, str(tmp_path)]


def test_ytdlp_command_missing_module_and_executables_uses_bootstrap(monkeypatch):
    monkeypatch.delenv('STREAM_TRANSLATOR_YTDLP_ADDON', raising=False)
    monkeypatch.setattr(audio_getter.importlib.util, 'find_spec', lambda name: None)
    monkeypatch.setattr(audio_getter.os.path, 'exists', lambda path: False)
    monkeypatch.setattr(audio_getter.shutil, 'which', lambda name: None)
    assert audio_getter._resolve_ytdlp_command() == [
        audio_getter.sys.executable, '-c', audio_getter.YTDLP_MODULE_BOOTSTRAP]
