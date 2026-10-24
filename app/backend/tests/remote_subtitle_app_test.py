import ast
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from native_subtitle import NativeSubtitleWindow
from native_subtitle_sse import NativeSubtitleSseClient, TOKEN_HEADER
from remote_subtitle_app import SettingsStore, normalize_server_url


@pytest.mark.parametrize("value,expected", [
    ("192.168.100.181:8765/", "http://192.168.100.181:8765"),
    (" localhost:8765 ", "http://localhost:8765"),
    ("https://example.com/subtitles///", "https://example.com/subtitles"),
    ("http://[::1]:8765/", "http://[::1]:8765"), ("", ""),
])
def test_normalize_server_url(value, expected):
    assert normalize_server_url(value) == expected


@pytest.mark.parametrize("value", [
    "ftp://host", "file:///tmp", "javascript:alert(1)", "https://",
    "http://host:bad", "http://host:99999", "http://a b", "http://host?query=1",
])
def test_reject_server_url(value):
    with pytest.raises(ValueError):
        normalize_server_url(value)


def test_settings_round_trip_and_atomic_replace(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.data["server_url"] = "http://host:8765"
    original_replace = os.replace
    replacements = []

    def replace(source, destination):
        assert Path(source).parent == path.parent
        assert Path(source) != path
        assert json.loads(Path(source).read_text(encoding="utf-8"))["server_url"] == "http://host:8765"
        replacements.append(source)
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    store.update_section("subtitle_settings", {"fontSize": 32, "mousePassthrough": True})
    store.save_window_state("floating_subtitle", {"x": 10, "y": 20, "width": 900, "height": 400})
    loaded = SettingsStore(path).get_config()
    assert loaded["server_url"] == "http://host:8765"
    assert loaded["subtitle_settings"]["fontSize"] == 32
    assert loaded["subtitle_settings"]["mousePassthrough"] is True
    assert loaded["ui"]["windows"]["floating_subtitle"]["width"] == 900
    assert len(replacements) == 2
    assert not list(tmp_path.glob("*.tmp"))
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")


@pytest.mark.parametrize("content", [None, "{broken", "[]", '{"ui":null}', '{"subtitle_settings":{"fontSize":"bad"}}'])
def test_settings_invalid_or_missing_falls_back(tmp_path, content):
    path = tmp_path / "settings.json"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    store = SettingsStore(path)
    assert store.get_config()["server_url"] == ""
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(store)
    try:
        assert window.settings["fontSize"] == 18
    finally:
        window.close()
        app.processEvents()


def test_non_object_settings_are_preserved_as_bad(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    store = SettingsStore(path)
    store.save()
    assert (tmp_path / "settings.json.bad").read_text(encoding="utf-8") == "[1, 2]"
    assert json.loads(path.read_text(encoding="utf-8"))["server_url"] == ""


def test_failed_atomic_write_preserves_previous_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.save()
    before = path.read_bytes()
    monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk failure")))
    store.data["server_url"] = "http://new-host"
    with pytest.raises(OSError):
        store.save()
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_stop_control_omitted_and_does_not_handle_click():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(on_stop_translation=None)
    try:
        window._set_controls_visible(True)
        painter = Mock()
        window._paint_controls(painter)
        assert window._stop_rect() not in [call.args[0] for call in painter.drawEllipse.call_args_list]
        window.update_subtitle_json('{"original":"保留字幕"}')
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=window._stop_rect().center())
        assert len(window._lines) == 1
        assert window._clear_rect() == window._control_rect(2)
        assert window._close_rect() == window._control_rect(3)
        stopped = Mock()
        window.on_stop_translation = stopped
        assert window._stop_rect() == window._control_rect(2)
        assert window._clear_rect() == window._control_rect(3)
        assert window._close_rect() == window._control_rect(4)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=window._stop_rect().center())
        stopped.assert_called_once()
    finally:
        window.close()
        app.processEvents()


def test_empty_token_sends_no_auth_header():
    app = QApplication.instance() or QApplication([])
    client = NativeSubtitleSseClient("http://host:8765", token="")
    request = client._request("/api/translation/active-task")
    assert not request.hasRawHeader(TOKEN_HEADER.encode("ascii"))
    assert bytes(request.rawHeader(b"Accept")) == b"application/json, text/event-stream"
    authenticated = NativeSubtitleSseClient("http://host", token="example")
    assert bytes(authenticated._request("/").rawHeader(TOKEN_HEADER.encode("ascii"))) == b"example"


def test_token_header_matches_admin_auth():
    from backend.core.admin_auth import TOKEN_HEADER as admin_header
    assert TOKEN_HEADER == admin_header


def test_default_token_retains_main_app_auth(monkeypatch):
    from backend.core import admin_auth
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(admin_auth, "get_admin_token", lambda: "main-app-token")
    client = NativeSubtitleSseClient("http://localhost")
    assert bytes(client._request("/").rawHeader(admin_auth.TOKEN_HEADER.encode("ascii"))) == b"main-app-token"


def test_server_change_clears_history_and_stops_previous_client(tmp_path, monkeypatch):
    import remote_subtitle_app as remote
    app = QApplication.instance() or QApplication([])
    # 保留真實 Qt signals 與請求物件，但不發出網路請求。
    monkeypatch.setattr(NativeSubtitleSseClient, "start", lambda self: None)
    controller = remote.RemoteSubtitleApp(app, SettingsStore(tmp_path / "settings.json"), "http://first:8765")
    try:
        previous = controller.client
        previous.stop = Mock(wraps=previous.stop)
        controller.window.begin_task("same-task-id")
        controller.window.update_subtitle_json('{"original":"舊主機字幕"}')
        settings = dict(controller.window.settings)
        settings["mousePassthrough"] = True
        controller.apply_settings("http://second:8765", settings)
        previous.stop.assert_called_once()
        assert controller.client is not previous
        assert controller.client.base_url == "http://second:8765"
        assert controller.window._lines == []
        assert controller.window._task_id is None
        expected_state = controller.state_text
        previous.taskStarted.emit("late")
        previous.subtitleReceived.emit('{"original":"late"}')
        previous.connectionStateChanged.emit("connected")
        assert controller.window._task_id is None
        assert controller.window._lines == []
        assert controller.state_text == expected_state
        assert controller.passthrough.isChecked()
        controller.client.taskStarted.emit("same-task-id")
        controller.client.asrReadyChanged.emit(True)
        controller.client.subtitleReceived.emit('{"original":"新主機字幕"}')
        assert controller.window._asr_ready is True
        assert controller.window._lines[0]["original"] == "新主機字幕"
        controller.client.connectionStateChanged.emit("waiting")
        assert controller.dialog.status.text() == "等待主機翻譯"
        assert "等待主機翻譯" in controller.tray.toolTip()
        # 等待中的每次輪詢不應讓狀態閃回「連線中」。
        controller.client.connectionStateChanged.emit("discovering")
        assert controller.dialog.status.text() == "等待主機翻譯"
        controller.client.connectionStateChanged.emit("connected")
        assert controller.dialog.status.text() == "已連線"
    finally:
        controller.shutdown()
        controller.window.removeEventFilter(controller)
        controller.window.close()
        controller.dialog.close()
        app.processEvents()


def test_remote_import_and_client_do_not_load_backend():
    app_dir = Path(__file__).resolve().parents[2]
    script = """
import sys
import remote_subtitle_app
from PyQt6.QtWidgets import QApplication
app = QApplication([])
client = remote_subtitle_app.NativeSubtitleSseClient('http://host', token='')
assert not any(name == 'backend' or name.startswith('backend.') for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=app_dir,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("running,ready", [(True, True), (True, False), (False, True)])
def test_public_status_minimal_payload_and_sharing_guard(running, ready):
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.responses import JSONResponse
    from fastapi.testclient import TestClient

    # 與 static_files_test 相同：擷取真實 handler，避免載入模型。
    source = Path(__file__).resolve().parents[1] / "public_app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    names = {"public_get_task_status", "subtitle_sharing_guard"}
    nodes = [node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name in names]
    app = FastAPI()
    enabled = True
    context = SimpleNamespace(running=running, asr_ready=ready, url="private-source")
    namespace = {"public_app": app, "HTTPException": HTTPException, "Request": Request,
                 "JSONResponse": JSONResponse, "_is_subtitle_sharing_enabled": lambda: enabled,
                 "get_task": lambda task: context if task == "known" else None}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    with TestClient(app) as client:
        response = client.get("/api/translation/status/known")
        assert response.status_code == 200
        assert response.json() == {"success": True, "task_id": "known", "is_running": running,
                                   "asr_ready": running and ready}
        assert "url" not in response.json()
        assert client.get("/api/translation/status/missing").status_code == 404
        enabled = False
        assert client.get("/api/translation/status/known").status_code == 404


def test_settings_bom_and_independent_validation(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"server_url": "ftp://invalid",
                               "subtitle_settings": {"fontSize": 42},
                               "ui": {"windows": {"floating_subtitle": {"width": 800}}}}),
                    encoding="utf-8-sig")
    data = SettingsStore(str(path)).get_config()
    assert data["server_url"] == ""
    assert data["subtitle_settings"]["fontSize"] == 42
    assert data["ui"]["windows"]["floating_subtitle"]["width"] == 800


def test_corrupt_settings_preserved(tmp_path):
    path = tmp_path / "settings.json"
    backup = tmp_path / "settings.json.bad"
    backup.write_text("older", encoding="utf-8")
    path.write_text("{broken", encoding="utf-8")
    store = SettingsStore(path)
    assert backup.read_text(encoding="utf-8") == "{broken"
    store.save()
    assert backup.read_text(encoding="utf-8") == "{broken"
    assert json.loads(path.read_text(encoding="utf-8")) == store.data


def test_unreadable_settings_cannot_be_overwritten_without_backup(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text('{"server_url":"http://saved"}', encoding="utf-8")
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", Mock(side_effect=OSError("locked")))
        patch.setattr(Path, "replace", Mock(side_effect=OSError("locked")))
        store = SettingsStore(path)
        with pytest.raises(OSError):
            store.save()
    store.save()
    assert json.loads(path.with_name("settings.json.bad").read_text())["server_url"] == "http://saved"


def test_close_saves_geometry_and_shutdown_is_safe(tmp_path, monkeypatch):
    import remote_subtitle_app as remote
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(NativeSubtitleSseClient, "start", lambda self: None)
    controller = remote.RemoteSubtitleApp(app, SettingsStore(tmp_path / "settings.json"), "http://host")
    requested = Mock()
    controller.app = SimpleNamespace(quit=requested)
    window, client = controller.window, controller.client
    try:
        assert client.parent() is controller
        window.setGeometry(20, 30, 800, 400)
        window.close()
        requested.assert_called_once()
        app.processEvents()
        controller.shutdown()
        assert controller.store.get_config()["ui"]["windows"]["floating_subtitle"]["width"] == 800
        # 以替身模擬已被 Qt 刪除的物件；不在 sip 包裝物件上 monkeypatch，以免收尾時崩潰。
        controller.client = SimpleNamespace(stop=Mock(side_effect=RuntimeError("deleted")))
        controller.window = SimpleNamespace(_save_geometry=Mock(side_effect=RuntimeError("deleted")))
        controller.shutdown()
    finally:
        controller.client, controller.window = client, window
        controller.shutdown()
        window.removeEventFilter(controller)
        window.close()
        controller.dialog.close()
        app.processEvents()


def test_tray_passthrough_sync(tmp_path, monkeypatch):
    import remote_subtitle_app as remote
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(NativeSubtitleSseClient, "start", lambda self: None)
    controller = remote.RemoteSubtitleApp(app, SettingsStore(tmp_path / "settings.json"), "http://host")
    try:
        controller.passthrough.trigger()
        assert controller.window.settings["mousePassthrough"] is True
        assert controller.dialog.fields["mousePassthrough"].isChecked()
        controller.passthrough.trigger()
        assert controller.window.settings["mousePassthrough"] is False
        assert not controller.dialog.fields["mousePassthrough"].isChecked()
    finally:
        controller.shutdown()
        controller.window.removeEventFilter(controller)
        controller.window.close()
        controller.dialog.close()
        controller.deleteLater()


def test_reconnect_reports_state():
    app = QApplication.instance() or QApplication([])
    client = NativeSubtitleSseClient("http://host", token="")
    states = []
    client.connectionStateChanged.connect(states.append)
    client._schedule_reconnect()
    assert states == ["reconnecting"]


def test_non_object_payloads_are_ignored():
    from PyQt6.QtNetwork import QNetworkReply
    from sse_parser import SseEventParser
    QApplication.instance() or QApplication([])
    client = NativeSubtitleSseClient("http://host", token="")
    subtitles, ready = [], []
    client.subtitleReceived.connect(subtitles.append)
    client.asrReadyChanged.connect(ready.append)
    client._running = True
    client._current_task_id = "t"
    stream = Mock()
    stream.readAll.return_value = (b"event: subtitle\ndata: []\n\nevent: subtitle\ndata: 1\n\n"
                                   b"event: status\ndata: [1]\n\nevent: status\ndata: \"x\"\n\n"
                                   b"event: subtitle\ndata: {\"original\": \"ok\"}\n\n")
    client._stream_reply = stream
    client._parser = SseEventParser()
    client._stream_ready_read(stream)
    assert subtitles == ['{"original": "ok"}']
    assert ready == []
    readiness = Mock()
    readiness.readAll.return_value = b"[]"
    readiness.error.return_value = QNetworkReply.NetworkError.NoError
    client._readiness_reply = readiness
    client._readiness_finished(readiness, "t")
    assert ready == []
    window = NativeSubtitleWindow()
    try:
        for payload in ("[]", "1", '"x"', "null"):
            window.update_subtitle_json(payload)
        assert window._lines == []
    finally:
        window.close()


def test_crash_guard_logs_instead_of_aborting(monkeypatch, caplog):
    import remote_subtitle_app as remote
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    remote.install_crash_guard()
    try:
        raise AttributeError("boom")
    except AttributeError:
        sys.excepthook(*sys.exc_info())
    assert "Unhandled exception" in caplog.text


def test_file_logging_writes_to_settings_folder(tmp_path):
    import logging
    import remote_subtitle_app as remote
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    try:
        remote.setup_file_logging(tmp_path)
        added = [handler for handler in root.handlers if handler not in before]
        assert len(added) == 1
        logging.getLogger("remote_subtitle_app").warning("寫入測試")
        added[0].flush()
        assert "寫入測試" in (tmp_path / "remote-subtitle.log").read_text(encoding="utf-8")
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)


def test_main_invalid_server_falls_back(tmp_path, monkeypatch):
    import remote_subtitle_app as remote
    QApplication.instance() or QApplication([])
    store = SettingsStore(tmp_path / "settings.json")
    store.data["server_url"] = "http://saved"
    controller = Mock()
    factory = Mock(return_value=controller)
    # 只替換模組內的名稱；改寫 PyQt 類別屬性在還原時會讓直譯器崩潰。
    fake_app = Mock()
    fake_app.exec.return_value = 0
    message_box = Mock()
    monkeypatch.setattr(remote, "QApplication", lambda args: fake_app)
    monkeypatch.setattr(remote, "SettingsStore", lambda: store)
    monkeypatch.setattr(remote, "RemoteSubtitleApp", factory)
    monkeypatch.setattr(remote, "QMessageBox", message_box)
    monkeypatch.setattr(remote, "QTimer", SimpleNamespace(singleShot=lambda delay, callback: callback()))
    monkeypatch.setattr(remote, "setup_file_logging", lambda directory: None)
    monkeypatch.setattr(sys, "excepthook", sys.excepthook)
    assert remote.main(["--server", "ftp://invalid"]) == 0
    message_box.warning.assert_called_once()
    assert factory.call_args.args[2] == "http://saved"
    controller.open_settings.assert_called_once()
