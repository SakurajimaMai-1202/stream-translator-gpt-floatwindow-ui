import io
import sys

import stream_translator_gpt.common as common


def test_configure_utf8_stdio_reconfigures_windows_streams(monkeypatch):
    stdout_bytes = io.BytesIO()
    stderr_bytes = io.BytesIO()
    stdout = io.TextIOWrapper(stdout_bytes, encoding="cp950")
    stderr = io.TextIOWrapper(stderr_bytes, encoding="cp950")
    monkeypatch.setattr(common.os, "name", "nt")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)

    common.configure_utf8_stdio()

    assert sys.stdout.encoding.lower().replace("-", "") == "utf8"
    assert sys.stderr.encoding.lower().replace("-", "") == "utf8"
    sys.stdout.write("日本語ー\n")
    sys.stdout.flush()
    assert "日本語ー" in stdout_bytes.getvalue().decode("utf-8")
