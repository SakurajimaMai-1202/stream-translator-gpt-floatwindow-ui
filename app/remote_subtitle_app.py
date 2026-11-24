"""獨立遠端字幕：僅使用 PyQt6 與標準函式庫。"""
from __future__ import annotations

import argparse
import copy
import ctypes
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

from PyQt6.QtCore import QEvent, QLockFile, QObject, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QDialog, QDialogButtonBox,
    QFormLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSpinBox, QStyle, QSystemTrayIcon,
)

from native_subtitle import NativeSubtitleWindow
from native_subtitle_sse import NativeSubtitleSseClient

APP_NAME = "Stream Translator Remote Subtitle"
APP_USER_MODEL_ID = "StreamTranslator.RemoteSubtitle"
logger = logging.getLogger(__name__)

NUMBERS = {
    "fontSize": ("字體大小", 10, 200, 16),
    "fontWeight": ("字重", 100, 900, 700),
    "maxDisplayCount": ("顯示筆數", 1, 100, 5),
    "backgroundOpacity": ("背景透明度（0 全透明／100 不透明）", 0, 100, 5),
}
CHECKS = {
    "showOriginal": ("顯示原文", True), "showTranslated": ("顯示譯文", True),
    "showTimestamp": ("顯示時間", False), "showLatency": ("顯示延遲", False),
    "mousePassthrough": ("滑鼠穿透", False),
}
COLORS = {
    "textColor": ("原文顏色", "#55FFFF"), "translatedColor": ("譯文顏色", "#FFDD00"),
    "timestampColor": ("時間顏色", "#FF5500"), "latencyColor": ("延遲顏色", "#AAFF00"),
    "backgroundColor": ("背景顏色", "#FFFFFF"),
}


SHARE_PAGES = ("desktop", "mobile", "subtitle")


def normalize_server_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    if "://" not in value:
        # host:port 不是 URL scheme；其餘顯式 scheme 一律拒絕。
        if re.match(r"^[a-zA-Z][\w+.-]*:", value) and not re.match(r"^[^/:?#]+:\d+(?:[/?#]|$)", value):
            raise ValueError("主機位址僅支援 http 或 https")
        value = "http://" + value
    try:
        parts = urlsplit(value)
        _ = parts.port  # 驗證連接埠範圍與格式。
        if (parts.scheme.lower() not in ("http", "https") or not parts.hostname
                or parts.username is not None or parts.password is not None
                or any(c.isspace() or ord(c) < 32 for c in value)):
            raise ValueError
    except ValueError:
        raise ValueError("請輸入有效的 http 或 https 網址") from None
    # 接受直接貼上的分享連結（…/desktop、…/mobile?x=1）；只保留網址前綴。
    path = parts.path.rstrip("/")
    page = path.rsplit("/", 1)[-1].lower()
    if page in SHARE_PAGES:
        path = path[: -len(page)].rstrip("/")
    return f"{parts.scheme.lower()}://{parts.netloc}{path}"


class SettingsStore:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME / "settings.json"
        self.data = {"server_url": "", "subtitle_settings": {}, "ui": {"windows": {}}}
        self._needs_backup = False
        try:
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict):
                raise ValueError("settings root is not an object")
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            logger.warning("Cannot load settings %s: %s", self.path, error)
            self._needs_backup = True
            try:
                self._backup_bad_file()
            except OSError as backup_error:
                logger.warning("Cannot preserve settings %s: %s", self.path, backup_error)
            return
        server = data.get("server_url", "")
        if isinstance(server, str):
            try:
                self.data["server_url"] = normalize_server_url(server)
            except ValueError as error:
                logger.warning("Invalid saved server URL: %s", error)
        settings = data.get("subtitle_settings")
        if isinstance(settings, dict):
            for key, (_, low, high, default) in NUMBERS.items():
                value = settings.get(key, default)
                if type(value) is int and low <= value <= high:
                    self.data["subtitle_settings"][key] = value
            for key, (_, default) in CHECKS.items():
                value = settings.get(key, default)
                if type(value) is bool:
                    self.data["subtitle_settings"][key] = value
            for key, (_, default) in COLORS.items():
                value = settings.get(key, default)
                if isinstance(value, str) and QColor(value).isValid():
                    self.data["subtitle_settings"][key] = value
        geometry = data.get("ui")
        for key in ("windows", "floating_subtitle"):
            geometry = geometry.get(key) if isinstance(geometry, dict) else None
        if isinstance(geometry, dict):
            self.data["ui"]["windows"]["floating_subtitle"] = {
                key: value for key, value in geometry.items()
                if key in ("x", "y", "width", "height") and type(value) is int
                and abs(value) < 100000 and (key in ("x", "y") or value > 0)
            }

    def _backup_bad_file(self):
        if self._needs_backup:
            self.path.replace(self.path.with_name(self.path.name + ".bad"))
            self._needs_backup = False

    def get_config(self):
        return copy.deepcopy(self.data)

    def save(self):
        self._backup_bad_file()
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="settings-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(self.data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)

    def update_section(self, section, values):
        self.data.setdefault(section, {}).update(values)
        # 視窗幾何與穿透切換不應因磁碟寫入失敗而中斷 Qt 事件。
        try:
            self.save()
        except OSError as error:
            logger.warning("Cannot save settings %s: %s", self.path, error)

    def save_window_state(self, name, values):
        self.data.setdefault("ui", {}).setdefault("windows", {})[name] = dict(values)
        try:
            self.save()
        except OSError as error:
            logger.warning("Cannot save settings %s: %s", self.path, error)


class SettingsDialog(QDialog):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        # 字幕視窗永遠置頂；設定視窗也置頂，避免被字幕蓋住。
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowTitle("遠端字幕設定")
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        self.server = QLineEdit()
        self.server.setPlaceholderText("http://192.168.100.181:8765")
        self.server.setClearButtonEnabled(True)
        form.addRow("主機網址", self.server)
        hint = QLabel("可填區網 IP:8765、反向代理網域（https://…），"
                      "或直接貼上主程式的電腦端／行動端字幕連結。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray;")
        form.addRow("", hint)
        self.fields = {}
        for key, (label, low, high, _) in NUMBERS.items():
            widget = QSpinBox()
            widget.setRange(low, high)
            self.fields[key] = widget
            form.addRow(label, widget)
        for key, (label, _) in CHECKS.items():
            widget = QCheckBox()
            self.fields[key] = widget
            form.addRow(label, widget)
        for key, (label, _) in COLORS.items():
            widget = QPushButton()
            widget.clicked.connect(lambda checked=False, k=key: self.choose_color(k))
            self.fields[key] = widget
            form.addRow(label, widget)
        self.status = QLabel()
        form.addRow("連線狀態", self.status)
        buttons = QDialogButtonBox()
        buttons.addButton("套用", QDialogButtonBox.ButtonRole.ApplyRole).clicked.connect(self.apply)
        buttons.addButton("關閉", QDialogButtonBox.ButtonRole.RejectRole).clicked.connect(self.hide)
        form.addRow(buttons)

    def refresh(self):
        self.server.setText(self.controller.server_url)
        for key, widget in self.fields.items():
            value = self.controller.window.settings[key]
            if key in NUMBERS:
                widget.setValue(value)
            elif key in CHECKS:
                widget.setChecked(value)
            else:
                self.set_color(key, value)
        self.status.setText(self.controller.state_text)

    def set_color(self, key, value):
        self.fields[key].setText(value)
        self.fields[key].setStyleSheet(f"border: 2px solid {value}; padding: 4px;")

    def choose_color(self, key):
        color = QColorDialog.getColor(QColor(self.fields[key].text()), self, "選擇顏色")
        if color.isValid():
            self.set_color(key, color.name())

    def apply(self):
        try:
            server = normalize_server_url(self.server.text())
            settings = {
                key: (widget.value() if key in NUMBERS else widget.isChecked() if key in CHECKS else widget.text())
                for key, widget in self.fields.items()
            }
            self.controller.apply_settings(server, settings)
            self.server.setText(server)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "無法套用設定", str(error))


class RemoteSubtitleApp(QObject):
    def __init__(self, app: QApplication, store: SettingsStore, server_url: str):
        super().__init__(app)
        self.app, self.store = app, store
        self.server_url = server_url
        self.client = None
        self.state_text = "尚未設定主機"
        self.window = NativeSubtitleWindow(store, on_open_settings=self.open_settings, on_stop_translation=None)
        self.window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.window.installEventFilter(self)
        self.dialog = SettingsDialog(self)
        self.tray = QSystemTrayIcon(app.windowIcon(), self)
        self.menu = QMenu()
        self.menu.addAction("設定…", self.open_settings)
        self.passthrough = QAction("滑鼠穿透", self.menu)
        self.passthrough.setCheckable(True)
        self.passthrough.setChecked(bool(self.window.settings["mousePassthrough"]))
        self.passthrough.triggered.connect(self.window.toggle_mouse_passthrough)
        self.window.mousePassthroughChanged.connect(self.sync_passthrough)
        self.menu.addAction(self.passthrough)
        self.menu.addAction("顯示／隱藏字幕視窗", self.toggle_visibility)
        self.menu.addAction("結束", app.quit)
        self.tray.setContextMenu(self.menu)
        self.tray.show()
        app.aboutToQuit.connect(self.shutdown)
        self.window.show()
        self.connect_server()
        if not server_url:
            QTimer.singleShot(0, self.open_settings)

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() == QEvent.Type.Close:
            self.window._save_geometry()
            self.app.quit()
        return super().eventFilter(watched, event)

    def open_settings(self):
        self.dialog.refresh()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def sync_passthrough(self, enabled):
        self.passthrough.setChecked(enabled)
        self.dialog.fields["mousePassthrough"].setChecked(enabled)

    def toggle_visibility(self):
        self.window.setVisible(not self.window.isVisible())

    def connection_state(self, state):
        # 等待中每次輪詢都會先回報 discovering，略過以免狀態文字閃動。
        if state == "discovering" and self.state_text == "等待主機翻譯":
            return
        self.state_text = {
            "waiting": "等待主機翻譯", "discovering": "連線中", "connecting": "連線中",
            "connected": "已連線", "reconnecting": "重新連線中", "stopped": "尚未設定主機",
        }.get(state, "重新連線中")
        self.dialog.status.setText(self.state_text)
        self.tray.setToolTip(f"{APP_NAME}\n{self.state_text}")

    def connect_server(self):
        if self.client is not None:
            self.client.taskStarted.disconnect(self.window.begin_task)
            self.client.asrReadyChanged.disconnect(self.window.update_asr_ready)
            self.client.subtitleReceived.disconnect(self.window.update_subtitle_json)
            self.client.connectionStateChanged.disconnect(self.connection_state)
            self.client.stop()
            self.client.deleteLater()
            self.client = None
        self.window.clear_subtitles()
        self.window.update_asr_ready(False)
        self.window.update_recording_state(bool(self.server_url))
        self.connection_state("discovering" if self.server_url else "stopped")
        if self.server_url:
            self.client = NativeSubtitleSseClient(self.server_url, parent=self, token="")
            self.client.taskStarted.connect(self.window.begin_task)
            self.client.asrReadyChanged.connect(self.window.update_asr_ready)
            self.client.subtitleReceived.connect(self.window.update_subtitle_json)
            self.client.connectionStateChanged.connect(self.connection_state)
            self.client.start()

    def apply_settings(self, server, settings):
        previous = self.store.get_config()
        self.store.data["server_url"] = server
        self.store.data["subtitle_settings"].update(settings)
        try:
            self.store.save()
        except OSError:
            self.store.data = previous
            raise
        self.window.update_settings_json(json.dumps(settings))
        self.sync_passthrough(settings["mousePassthrough"])
        if server != self.server_url:
            self.server_url = server
            self.connect_server()

    def shutdown(self):
        if self.client is not None:
            try:
                self.client.stop()
            except RuntimeError:
                pass  # Qt may already have destroyed the client during teardown.
        try:
            self.window._save_geometry()
        except RuntimeError:
            pass  # Geometry was also saved before the close event requested quit.
        self.tray.hide()


def setup_file_logging(directory: Path) -> None:
    """視窗版 exe 沒有主控台；警告寫到設定資料夾的輪替檔案。"""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(directory / "remote-subtitle.log", maxBytes=1_000_000,
                                      backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)


def install_crash_guard() -> None:
    """PyQt6 遇到 slot 內未處理的例外會中止程序；改成只記錄。"""
    def hook(exc_type, exc, tb):
        logger.error("Unhandled exception", exc_info=(exc_type, exc, tb))
    sys.excepthook = hook


def main(argv=None):
    parser = argparse.ArgumentParser(description="遠端原生浮動字幕")
    parser.add_argument("--server", type=str, default=None)
    args = parser.parse_args(argv)
    install_crash_guard()
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    # Qt 6 預設啟用高 DPI，不需 Qt 5 的 AA_EnableHighDpiScaling。
    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    icon = QIcon(str(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "app_icon.ico"))
    if icon.isNull():
        icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    app.setWindowIcon(icon)
    store = SettingsStore()
    try:
        store.path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        QMessageBox.critical(None, APP_NAME, f"無法建立設定資料夾：{error}")
        return 1
    lock = QLockFile(str(store.path.parent / "remote-subtitle.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, APP_NAME, "遠端字幕已在執行")
        return 0
    setup_file_logging(store.path.parent)
    server = store.get_config()["server_url"]
    invalid_server = False
    # 空字串視同未指定，不覆蓋已存的主機位址。
    if args.server:
        try:
            server = normalize_server_url(args.server)
        except ValueError as error:
            QMessageBox.warning(None, "主機位址無效", str(error))
            invalid_server = True
    controller = RemoteSubtitleApp(app, store, server)
    if invalid_server and server:
        QTimer.singleShot(0, controller.open_settings)
    try:
        return app.exec()
    finally:
        lock.unlock()


if __name__ == "__main__":
    sys.exit(main())
