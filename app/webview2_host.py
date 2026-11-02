"""Qt 原生視窗中的 WebView2；.NET 僅在 start 載入。"""
import ctypes
from ctypes import wintypes
import importlib.util
import json
import logging
import os
import sys
from time import monotonic

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QWidget

import ui_perf
from backend.core.admin_auth import TOKEN_HEADER
from webview_engine import (BRIDGE_METHODS, build_bridge_script, parse_bridge_message,
                            resolve_webview2_dll_dir, url_origin, webview2_user_data_dir)

logger = logging.getLogger(__name__)


class _PendingCreation(QObject):
    """不可取消的 .NET 建立工作完成後，在 Qt 執行緒釋放結果。"""
    ready = pyqtSignal()
    outstanding = set()

    def __init__(self, task, controller_task):
        super().__init__(QApplication.instance())
        self.task = task
        self.controller_task = controller_task
        self.outstanding.add(self)
        self.ready.connect(self._finish, Qt.ConnectionType.QueuedConnection)
        from System import Action
        self.callback = Action(self._notify)
        self.task.GetAwaiter().OnCompleted(self.callback)

    def _notify(self):
        try:
            self.ready.emit()
        except Exception:
            logger.debug("應用程式已結束，略過建立工作通知")

    def _finish(self):
        try:
            if not self.task.IsFaulted and not self.task.IsCanceled and self.controller_task:
                self.task.Result.Close()
            elif self.task.IsFaulted:
                _ = self.task.Exception
        except Exception:
            logger.debug("釋放延遲完成的 WebView2 工作失敗", exc_info=True)
        finally:
            self.task = self.callback = None
            self.outstanding.discard(self)
            self.deleteLater()


class WebView2Host(QWidget):
    failed = pyqtSignal(str)
    loadFinished = pyqtSignal(bool)
    loadStarted = pyqtSignal()

    def __init__(self, parent, url, bridge, origins, token):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.url, self.origins, self.token = url, origins, token
        # 名稱來自固定白名單，絕不使用網頁提供的名稱查找 Python 屬性。
        self.dispatch = {name: getattr(bridge, name) for name in BRIDGE_METHODS}
        self.controller = self.core = self.environment = None
        self.task = None
        self.stage = ""
        self.handlers = []
        self._timers = set()
        self._navigation_generation = 0
        self._closed = self._failed = self._loaded = False
        self._navigation_attempts = 0
        self._reloads = []
        self._dll_handle = None
        self.poll = QTimer(self)
        self.poll.setInterval(10)
        self.poll.timeout.connect(self._poll)
        self.installEventFilter(self)
        parent.installEventFilter(self)
        parent.destroyed.connect(self.shutdown)
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def start(self):
        if self._closed:
            return
        try:
            if sys.platform != "win32":
                raise RuntimeError("WebView2 僅支援 Windows")
            if QApplication.instance() is None:
                raise RuntimeError("WebView2 需要 QApplication")
            from pythonnet import load
            load("netfx")
            import clr
            root = resolve_webview2_dll_dir(getattr(sys, "frozen", False),
                                           getattr(sys, "_MEIPASS", ""), importlib.util.find_spec)
            native = str(root / "runtimes/win-x64/native")
            self._dll_handle = os.add_dll_directory(native)
            os.environ["PATH"] = native + os.pathsep + os.environ.get("PATH", "")
            clr.AddReference("System.Drawing")
            clr.AddReference(str(root / "Microsoft.Web.WebView2.Core.dll"))
            from Microsoft.Web.WebView2.Core import (CoreWebView2Environment,
                CoreWebView2EnvironmentOptions, CoreWebView2MoveFocusReason, CoreWebView2WebResourceContext)
            from System import IntPtr
            from System.Drawing import Rectangle, Color
            self.IntPtr, self.Rectangle, self.Color = IntPtr, Rectangle, Color
            self.focus_reason = CoreWebView2MoveFocusReason.Programmatic
            self.resource_context = CoreWebView2WebResourceContext.All
            if not CoreWebView2Environment.GetAvailableBrowserVersionString(None):
                raise RuntimeError("未安裝 WebView2 Runtime")
            options = CoreWebView2EnvironmentOptions()
            debug = os.environ.get("STREAM_TRANSLATOR_WEBVIEW2_DEBUG_PORT", "")
            if debug:
                port = int(debug)
                if not 1 <= port <= 65535:
                    raise ValueError("WebView2 偵錯埠號無效")
                options.AdditionalBrowserArguments = f"--remote-debugging-address=127.0.0.1 --remote-debugging-port={port}"
            self.debug = bool(debug)
            self.task = CoreWebView2Environment.CreateAsync(None, str(webview2_user_data_dir(os.environ)), options)
            self.stage = "environment"
            self.deadline = monotonic() + 15
            self.poll.start()
        except Exception as exc:
            self._fail(f"WebView2 啟動失敗：{exc}")

    def _poll(self):
        try:
            if monotonic() > self.deadline:
                raise TimeoutError("WebView2 建立逾時（15 秒）")
            if self.task.IsCanceled or self.task.IsFaulted:
                raise RuntimeError(f"WebView2 {self.stage} 工作失敗：{self.task.Exception}")
            if not self.task.IsCompleted:
                return
            if self.stage == "environment":
                self.environment = self.task.Result
                self.task = self.environment.CreateCoreWebView2ControllerAsync(self.IntPtr(int(self.winId())))
                self.stage = "controller"
            elif self.stage == "controller":
                self.controller = self.task.Result
                self.core = self.controller.CoreWebView2
                self._configure()
                self.task = self.core.AddScriptToExecuteOnDocumentCreatedAsync(build_bridge_script(BRIDGE_METHODS, self.origins))
                self.stage = "script"
            else:
                self.poll.stop()
                self.task = None
                self.sync_host()
                self._later(20000, self._check_initial_navigation)
                self.core.Navigate(self.url)
        except Exception as exc:
            self._fail(f"WebView2 初始化失敗：{exc}")

    def _attach(self, source, event, callback):
        def guarded(sender, args):
            if self._closed:
                return
            try:
                callback(sender, args)
            except Exception:
                logger.exception("WebView2 事件處理失敗：%s", event)
        # pythonnet 事件必須使用 +=；保存委派直到解除訂閱。
        bound = getattr(source, event)
        bound += guarded
        self.handlers.append((source, event, guarded))

    def _configure(self):
        settings = self.core.Settings
        for name in ("IsZoomControlEnabled", "IsPinchZoomEnabled", "IsStatusBarEnabled",
                     "IsSwipeNavigationEnabled", "AreBrowserAcceleratorKeysEnabled",
                     "IsGeneralAutofillEnabled", "IsPasswordAutosaveEnabled"):
            setattr(settings, name, False)
        settings.AreDevToolsEnabled = self.debug
        self.controller.DefaultBackgroundColor = self.Color.FromArgb(255, 15, 23, 42)
        self.controller.AllowExternalDrop = False
        for scheme, host, port in self.origins:
            self.core.AddWebResourceRequestedFilter(f"{scheme}://{host}:{port}/*", self.resource_context)
        self._attach(self.core, "WebResourceRequested", self._request)
        self._attach(self.core, "NavigationStarting", self._navigation)
        self._attach(self.core, "NewWindowRequested", self._new_window)
        self._attach(self.core, "WebMessageReceived", self._message)
        self._attach(self.core, "NavigationCompleted", self._completed)
        self._attach(self.core, "ProcessFailed", self._process_failed)
        try:
            receiver = self.core.GetDevToolsProtocolEventReceiver("Runtime.consoleAPICalled")
            self._attach(receiver, "DevToolsProtocolEventReceived", self._console)
            self._console_task = self.core.CallDevToolsProtocolMethodAsync("Runtime.enable", "{}")
            self._later(100, self._check_console)
        except Exception:
            logger.warning("WebView2 console 轉送不可用", exc_info=True)

    def _check_console(self):
        task = self._console_task
        if task.IsCanceled or task.IsFaulted:
            logger.warning("WebView2 console 轉送不可用：Runtime.enable 失敗")
        elif not task.IsCompleted:
            self._later(100, self._check_console)

    def _request(self, sender, event):
        if url_origin(str(event.Request.Uri)) in self.origins:
            event.Request.Headers.SetHeader(TOKEN_HEADER, self.token)

    def _external(self, uri):
        url = QUrl(str(uri))
        if url.scheme().lower() in ("http", "https"):
            QDesktopServices.openUrl(url)

    def _navigation(self, sender, event):
        self._navigation_generation += 1
        if url_origin(str(event.Uri)) not in self.origins:
            event.Cancel = True
            self._external(event.Uri)
        else:
            self.loadStarted.emit()

    def _new_window(self, sender, event):
        event.Handled = True
        self._external(event.Uri)

    def _message(self, sender, event):
        if url_origin(str(event.Source)) not in self.origins:
            return
        message = parse_bridge_message(str(event.WebMessageAsJson))
        source_origin = url_origin(str(event.Source))
        generation = self._navigation_generation
        def invoke():
            if self._closed or generation != self._navigation_generation or url_origin(str(self.core.Source)) != source_origin:
                return
            result = None
            try:
                result = self.dispatch[message["method"]](*message["args"])
            except Exception:
                logger.exception("WebView2 bridge 執行失敗")
            if not self._closed and generation == self._navigation_generation and url_origin(str(self.core.Source)) == source_origin:
                try:
                    self.core.PostWebMessageAsJson(json.dumps({"id": message["id"], "result": result}))
                except Exception:
                    logger.exception("WebView2 bridge 回覆失敗")
        self._later(0, invoke)

    def _check_initial_navigation(self):
        if not self._closed and not self._loaded:
            self._fail("WebView2 首次頁面載入逾時（20 秒）")

    def _completed(self, sender, event):
        ok = bool(event.IsSuccess)
        self.loadFinished.emit(ok)
        if ok:
            self._loaded = True
        elif not self._loaded:
            self._navigation_attempts += 1
            if self._navigation_attempts <= 2:
                self._later(1200, lambda: self.core.Navigate(self.url))
            else:
                self._fail("WebView2 首頁載入失敗")

    def _process_failed(self, sender, event):
        kind = str(event.ProcessFailedKind)
        if "BrowserProcessExited" in kind:
            self._fail("WebView2 瀏覽器程序終止")
        elif "RenderProcess" in kind:
            now = monotonic()
            self._reloads = [when for when in self._reloads if now - when < 30]
            if len(self._reloads) >= 2:
                self._fail("WebView2 渲染程序重複失敗")
            else:
                self._reloads.append(now)
                self._later(1200, self.core.Reload)

    def _console(self, sender, event):
        data = json.loads(str(event.ParameterObjectAsJson))
        ui_perf.record_console_message()
        log = {"error": logger.error, "warning": logger.warning, "log": logger.info,
               "info": logger.info}.get(data.get("type"), logger.debug)
        frames = data.get("stackTrace", {}).get("callFrames", [])
        line = frames[0].get("lineNumber", 0) + 1 if frames else 0
        message = " ".join(str(arg.get("value", arg.get("description", ""))) for arg in data.get("args", []))
        log("[WebView Console] %s (Line: %s)", message, line)

    def _later(self, delay, callback):
        if self._closed:
            return
        timer = QTimer(self)
        timer.setSingleShot(True)
        self._timers.add(timer)
        def run():
            self._timers.discard(timer)
            timer.deleteLater()
            if not self._closed:
                try:
                    callback()
                except Exception as exc:
                    self._fail(f"WebView2 操作失敗：{exc}")
        timer.timeout.connect(run)
        timer.start(delay)

    def sync_host(self):
        if self.controller is None or self._closed:
            return
        window = self.window()
        self.setGeometry(window.contentsRect())
        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetClientRect(wintypes.HWND(int(self.winId())), ctypes.byref(rect)):
            raise OSError("GetClientRect 失敗")
        self.controller.Bounds = self.Rectangle(0, 0, rect.right, rect.bottom)
        self.controller.IsVisible = window.isVisible() and not window.isMinimized()

    def refocus(self):
        if self.controller is not None and QApplication.activeModalWidget() is None:
            self.controller.MoveFocus(self.focus_reason)

    def native_event(self, message):
        if sys.platform != "win32" or self._closed:
            return
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0007 or (msg.message == 0x0006 and msg.wParam & 0xFFFF):
            self._later(0, self.refocus)
            self._later(80, self.refocus)
        elif msg.message == 0x02E0:
            self._later(0, self.sync_host)
            self._later(120, self.sync_host)

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.Hide,
                            QEvent.Type.WindowStateChange, QEvent.Type.DevicePixelRatioChange):
            self._later(0, self.sync_host)
        elif obj is self.window() and event.type() == QEvent.Type.Move and self.controller is not None:
            self._later(0, self.controller.NotifyParentWindowPositionChanged)
            self._later(0, self.sync_host)
        return False

    def run_javascript(self, script):
        if self.core is not None and not self._closed:
            self.core.ExecuteScriptAsync(script)

    def _fail(self, reason):
        if self._failed or self._closed:
            return
        self._failed = True
        self.shutdown()
        self.failed.emit(reason)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.poll.stop()
        for timer in self._timers:
            timer.stop()
            timer.deleteLater()
        self._timers.clear()
        # WebView2 建立 API 沒有取消權杖；不等待工作，不留下輪詢 timer。
        # 若建立 controller 正在進行，完成時透過 Qt queued signal 立即關閉。
        if self.task is not None and self.stage in ("environment", "controller") and self.controller is None:
            try:
                _PendingCreation(self.task, self.stage == "controller")
            except Exception:
                logger.exception("無法註冊 WebView2 延遲釋放")
        for source, event, handler in self.handlers:
            try:
                bound = getattr(source, event)
                bound -= handler
            except Exception:
                logger.debug("解除 WebView2 事件失敗", exc_info=True)
        self.handlers.clear()
        if self.controller is not None:
            try:
                self.controller.Close()
            except Exception:
                logger.debug("關閉 WebView2 失敗", exc_info=True)
        self.controller = self.core = self.environment = self.task = None
        if self._dll_handle is not None:
            self._dll_handle.close()
            self._dll_handle = None
