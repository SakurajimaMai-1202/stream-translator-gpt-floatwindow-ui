from pathlib import Path
import queue
import threading

import numpy as np

from stream_translator_gpt import audio_getter
from stream_translator_gpt.common import AUDIO_STREAM_GAP


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
    output = queue.SimpleQueue()

    getter.loop(output)

    assert len(opens) == 2
    assert output.get() is AUDIO_STREAM_GAP
    assert output.get().shape == (audio_getter.SAMPLES_PER_FRAME,)
    assert output.get() is None
