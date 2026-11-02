"""不建立 QApplication 的引擎、安全政策與打包測試。"""
import ast
from argparse import Namespace
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace

import pytest

from webview_engine import (
    BRIDGE_METHODS, WEBVIEW_ENGINES, allowed_origins, build_bridge_script,
    parse_bridge_message, read_configured_engine, resolve_engine,
    resolve_webview2_dll_dir, url_origin, webview2_user_data_dir,
)

APP = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("platform,expected", [("win32", "webview2"), ("linux", "qtwebengine"), ("darwin", "qtwebengine")])
def test_engine_precedence(platform, expected):
    assert WEBVIEW_ENGINES == ("webview2", "qtwebengine")
    assert resolve_engine(Namespace(), "", platform) == expected
    assert resolve_engine(Namespace(), "qtwebengine", platform) == "qtwebengine"
    assert resolve_engine(Namespace(webview_engine="webview2"), "qtwebengine", platform) == "webview2"
    assert resolve_engine(Namespace(webview_engine="qtwebengine"), "webview2", platform) == "qtwebengine"


@pytest.mark.parametrize("value", ["unknown", 12, [], {}, True])
def test_invalid_engine_uses_platform_default(value, caplog):
    assert resolve_engine(Namespace(webview_engine=value), "qtwebengine", "win32") == "webview2"
    assert resolve_engine(Namespace(), value, "linux") == "qtwebengine"
    assert caplog.records


@pytest.mark.parametrize("content,expected", [
    ("ui: {webview_engine: webview2}", "webview2"),
    ("ui: {webview_engine: ' QTWEBENGINE '}", "qtwebengine"),
    ("ui: {webview_engine: invalid}", ""),
    ("ui: {webview_engine: 12}", ""), ("ui: []", ""),
    ("ui: {webview_engine: [webview2]}", ""), ("[bad", ""), ("", ""),
])
def test_config_reader(tmp_path, content, expected):
    path = tmp_path / "config.yaml"
    path.write_text(content, encoding="utf-8")
    assert read_configured_engine(path) == expected
    assert read_configured_engine(tmp_path / "missing.yaml") == ""


@pytest.mark.parametrize("uri,expected", [
    ("http://127.0.0.1:8000/", True), ("http://localhost:8000/path?q=a", True),
    ("HTTP://LOCALHOST:5173/", True), ("http://127.0.0.1:5173/", True),
    ("http://localhost:8001/", False), ("http://localhost/", False),
    ("http://localhost:0/", False), ("https://localhost:8000/", False),
    ("http://localhost.:8000/", False), ("http://[::1]:8000/", False),
    ("http://localhost.evil.com:8000/", False),
    ("http://127.0.0.1:8000@evil.com/", False),
    ("http://localhost:5173@evil.com/", False),
    ("http://evil.com@localhost:8000/", True),
    ("http://localhost:invalid/", False), ("http://[broken", False),
    ("null", False), ("", False), (None, False), ("file:///localhost:8000", False),
])
def test_origin_policy(uri, expected):
    assert (url_origin(uri) in allowed_origins(8000, 5173)) is expected


def test_no_frontend_port_or_other_hosts():
    assert allowed_origins(8000) == {("http", "127.0.0.1", 8000), ("http", "localhost", 8000)}
    assert url_origin("http://localhost/") in allowed_origins(80)


@pytest.mark.parametrize("method", list(BRIDGE_METHODS))
def test_valid_bridge_messages(method):
    args = [True if kind is bool else "文字" for kind in BRIDGE_METHODS[method]]
    message = {"id": 1, "method": method, "args": args}
    assert parse_bridge_message(json.dumps(message)) == message


@pytest.mark.parametrize("raw", [
    "not json", "null", "[]", "{}",
    json.dumps({"id": 1, "method": "__getattribute__", "args": []}),
    json.dumps({"id": 1, "method": "close", "args": []}),
    json.dumps({"id": True, "method": "openInBrowser", "args": []}),
    json.dumps({"id": "1", "method": "openInBrowser", "args": []}),
    json.dumps({"id": 0, "method": "openInBrowser", "args": []}),
    json.dumps({"id": -1, "method": "openInBrowser", "args": []}),
    json.dumps({"id": 2**53, "method": "openInBrowser", "args": []}),
    json.dumps({"id": 1, "method": [], "args": []}),
    json.dumps({"id": 1, "method": "openInBrowser", "args": {}}),
    json.dumps({"id": 1, "method": "openInBrowser", "args": ["extra"]}),
    json.dumps({"id": 1, "method": "copyToClipboard", "args": [False]}),
    json.dumps({"id": 1, "method": "updateNativeRecordingState", "args": [1]}),
    json.dumps({"id": 1, "method": "openInBrowser", "args": [], "extra": 1}),
])
def test_reject_malformed_messages(raw):
    with pytest.raises(ValueError):
        parse_bridge_message(raw)


def test_script_has_only_explicit_methods_and_origin_frame_guards():
    script = build_bridge_script(BRIDGE_METHODS, allowed_origins(8000, 5173))
    names = json.loads(re.search(r"for \(const method of (\[.*?\])\)", script).group(1))
    assert set(names) == set(BRIDGE_METHODS)
    assert "window.pyqt = {}" in script
    assert "Proxy" not in script
    assert "window !== window.top" in script
    assert "location.origin" in script
    assert "http://localhost:8000" in script
    assert "window.__FW_WEBVIEW2__ = true" in script
    assert "new Promise" in script and "callback(result)" in script
    with pytest.raises(ValueError):
        build_bridge_script(["evil"])


def _dlls(root):
    for relative in ("Microsoft.Web.WebView2.Core.dll", "runtimes/win-x64/native/WebView2Loader.dll"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return root


def test_frozen_dll_layout(tmp_path):
    root = _dlls(tmp_path / "webview2_runtime")
    def forbidden(name):
        raise AssertionError("frozen 路徑不得查詢 pywebview")
    assert resolve_webview2_dll_dir(True, tmp_path, forbidden) == root


@pytest.mark.parametrize("locations", [True, False])
def test_source_dll_layout(tmp_path, locations):
    package = tmp_path / "webview"
    root = _dlls(package / "lib")
    def find_spec(name):
        assert name == "webview"
        return SimpleNamespace(submodule_search_locations=[str(package)] if locations else None,
                               origin=str(package / "__init__.py"))
    assert resolve_webview2_dll_dir(False, None, find_spec) == root


@pytest.mark.parametrize("missing", ["Microsoft.Web.WebView2.Core.dll", "runtimes/win-x64/native/WebView2Loader.dll"])
def test_missing_dlls(tmp_path, missing):
    root = _dlls(tmp_path / "webview2_runtime")
    (root / missing).unlink()
    with pytest.raises(RuntimeError, match=Path(missing).name):
        resolve_webview2_dll_dir(True, tmp_path, lambda _: None)
    with pytest.raises(RuntimeError):
        resolve_webview2_dll_dir(False, None, lambda _: None)


def test_data_dir(tmp_path):
    assert webview2_user_data_dir({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "StreamTranslator" / "WebView2"
    assert webview2_user_data_dir({"STREAM_TRANSLATOR_WEBVIEW2_DATA_DIR": str(tmp_path)}) == tmp_path
    with pytest.raises(RuntimeError):
        webview2_user_data_dir({})


def test_import_is_qt_and_dotnet_free():
    script = """
import builtins, sys
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def checked(name, *args, **kwargs):
    assert name.split('.')[0] not in {'PyQt6', 'pythonnet', 'clr', 'webview'}, name
    return original(name, *args, **kwargs)
builtins.__import__ = checked
import webview_engine
assert not any(name.split('.')[0] in {'PyQt6', 'pythonnet', 'clr', 'webview'} for name in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-B", "-c", script, str(APP)], check=True)


def test_host_has_no_module_level_dotnet_imports():
    tree = ast.parse((APP / "webview2_host.py").read_text(encoding="utf-8"))
    def visit(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return
        if isinstance(node, ast.Import):
            assert all(alias.name.split('.')[0] not in {"pythonnet", "clr", "webview"} for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split('.')[0] not in {"pythonnet", "clr", "webview"}
        for child in ast.iter_child_nodes(node):
            visit(child)
    visit(tree)


def test_allowlist_matches_home_bridge_slots():
    tree = ast.parse((APP / "windows.py").read_text(encoding="utf-8"))
    bridge = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HomeBridge")
    slots = {
        method.name for method in bridge.body if isinstance(method, ast.FunctionDef)
        and any(isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "pyqtSlot" for decorator in method.decorator_list)
    }
    assert slots == set(BRIDGE_METHODS)


def test_home_native_event_does_not_call_super():
    tree = ast.parse((APP / "windows.py").read_text(encoding="utf-8-sig"))
    home = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HomeWindow")
    method = next(node for node in home.body if isinstance(node, ast.FunctionDef) and node.name == "nativeEvent")
    # Calling super() here crashes the process with an access violation.
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                   and node.func.id == "super" for node in ast.walk(method))


def test_host_does_not_shadow_qwidget_close():
    tree = ast.parse((APP / "webview2_host.py").read_text(encoding="utf-8-sig"))
    host = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "WebView2Host")
    assert not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and node.name == "close" for node in host.body)
