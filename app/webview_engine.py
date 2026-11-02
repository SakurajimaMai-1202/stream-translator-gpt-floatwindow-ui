"""WebView 引擎與安全政策；不載入 Qt、.NET 或 pywebview。"""
import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)
WEBVIEW_ENGINES = ("webview2", "qtwebengine")
BRIDGE_METHODS = {
    "openInBrowser": (), "openSubtitleWindow": (),
    "updateNativeSubtitleSettings": (str,), "updateNativeRecordingState": (bool,),
    "applyAppUpdate": (str, str), "chooseLocalFile": (),
    "chooseFolder": (str, str), "chooseFile": (str, str, str),
    "copyToClipboard": (str,), "saveTextFile": (str, str), "saveBinaryFile": (str, str),
}


def read_configured_engine(config_path):
    try:
        import yaml
        path = Path(config_path)
        if not path.exists():
            return ""
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        value = (config.get("ui") or {}).get("webview_engine", "")
        if not isinstance(value, str) or (value and value.strip().lower() not in WEBVIEW_ENGINES):
            logger.warning("無效的 ui.webview_engine，使用預設引擎")
            return ""
        return value.strip().lower()
    except Exception:
        logger.warning("讀取 WebView 引擎設定失敗，使用預設引擎")
        return ""


def resolve_engine(args, configured, platform=sys.platform):
    default = "webview2" if platform == "win32" else "qtwebengine"
    value = getattr(args, "webview_engine", None)
    if value is None:
        value = configured or default
    if isinstance(value, str) and value.strip().lower() in WEBVIEW_ENGINES:
        return value.strip().lower()
    logger.warning("無效的 WebView 引擎，使用預設引擎")
    return default


def allowed_origins(backend_port, frontend_port=None):
    ports = {backend_port}
    if frontend_port is not None:
        ports.add(frontend_port)
    return {("http", host, port) for host in ("127.0.0.1", "localhost") for port in ports}


def url_origin(url):
    try:
        parsed = urlsplit(url)
        return (parsed.scheme.lower(), (parsed.hostname or "").lower(), parsed.port if parsed.port is not None else 80)
    except (TypeError, ValueError):
        return None


def build_bridge_script(methods, origins=()):
    names = list(methods)
    if any(name not in BRIDGE_METHODS for name in names):
        raise ValueError("不允許的 bridge 方法")
    urls = [f"{scheme}://{host}" + (f":{port}" if port != 80 else "") for scheme, host, port in sorted(origins)]
    return """(() => {
      if (window !== window.top || !ORIGINS.includes(location.origin)) return;
      window.__FW_WEBVIEW2__ = true;
      let sequence = 0;
      const pending = new Map();
      window.chrome.webview.addEventListener('message', event => {
        const message = event.data;
        const finish = pending.get(message.id);
        if (finish) { pending.delete(message.id); finish(message.result); }
      });
      window.pyqt = {};
      for (const method of METHODS) {
        window.pyqt[method] = (...args) => {
          const callback = typeof args[args.length - 1] === 'function' ? args.pop() : null;
          return new Promise(resolve => {
            const id = ++sequence;
            pending.set(id, result => {
              try { if (callback) callback(result); } finally { resolve(result); }
            });
            window.chrome.webview.postMessage({id, method, args});
          });
        };
      }
    })();""".replace("ORIGINS", json.dumps(urls)).replace("METHODS", json.dumps(names))


def parse_bridge_message(raw):
    try:
        message = json.loads(raw)
        if not isinstance(message, dict) or set(message) != {"id", "method", "args"}:
            raise ValueError()
        identifier, method, args = message["id"], message["method"], message["args"]
        if type(identifier) is not int or not 0 < identifier <= 9007199254740991:
            raise ValueError()
        if not isinstance(method, str) or method not in BRIDGE_METHODS or not isinstance(args, list):
            raise ValueError()
        signature = BRIDGE_METHODS[method]
        if len(args) != len(signature) or any(type(arg) is not kind for arg, kind in zip(args, signature)):
            raise ValueError()
        return message
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("無效的 bridge 訊息") from exc


def resolve_webview2_dll_dir(frozen, meipass, find_spec):
    if frozen:
        root = Path(meipass) / "webview2_runtime"
    else:
        spec = find_spec("webview")
        if spec is None:
            raise RuntimeError("找不到 pywebview 的 WebView2 DLL")
        locations = spec.submodule_search_locations
        root = (Path(next(iter(locations))) if locations else Path(spec.origin).parent) / "lib"
    for relative in ("Microsoft.Web.WebView2.Core.dll", "runtimes/win-x64/native/WebView2Loader.dll"):
        if not (root / relative).is_file():
            raise RuntimeError(f"缺少 WebView2 DLL：{root / relative}")
    return root


def webview2_user_data_dir(environ):
    override = environ.get("STREAM_TRANSLATOR_WEBVIEW2_DATA_DIR")
    if override:
        return Path(override)
    if not environ.get("LOCALAPPDATA"):
        raise RuntimeError("缺少 LOCALAPPDATA，無法建立 WebView2 資料目錄")
    return Path(environ["LOCALAPPDATA"]) / "StreamTranslator" / "WebView2"


def bundled_dotnet_files(meipass):
    """Return only bundled assemblies and loaders that may carry download marks."""
    root = Path(meipass)
    return [
        root / "pythonnet/runtime/Python.Runtime.dll",
        *sorted((root / "clr_loader/ffi/dlls").rglob("ClrLoader.dll")),
        root / "webview2_runtime/Microsoft.Web.WebView2.Core.dll",
        root / "webview2_runtime/runtimes/win-x64/native/WebView2Loader.dll",
    ]


def clear_download_mark(path):
    """Best effort removal, including on read-only installs."""
    try:
        os.remove(f"{path}:Zone.Identifier")
    except (FileNotFoundError, OSError):
        logger.debug("Could not remove download mark from %s", path, exc_info=True)
