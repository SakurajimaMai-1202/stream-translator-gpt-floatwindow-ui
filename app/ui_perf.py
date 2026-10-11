"""Opt-in responsiveness diagnostics for the desktop shell.

Set ``STREAM_TRANSLATOR_UI_PERF=1`` to log Qt main-thread stalls.  Chromium
renders pages in its own process, but QWebEngineView windows still receive
input and present frames through the Qt main thread, so a stall measured here
is felt as lag in Home and Settings.
"""

from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QElapsedTimer, QEvent, QObject, QTimer, Qt


logger = logging.getLogger(__name__)

PERF_ENV = "STREAM_TRANSLATOR_UI_PERF"
REPORT_MS_ENV = "STREAM_TRANSLATOR_UI_PERF_REPORT_MS"


def perf_enabled() -> bool:
    return os.environ.get(PERF_ENV, "").strip() == "1"


class MainThreadStallMonitor(QObject):
    """Measure how late a fast timer fires; lateness is time the loop was blocked."""

    def __init__(
        self,
        parent: QObject | None = None,
        interval_ms: int = 10,
        stall_ms: int = 50,
        report_ms: int = 10_000,
    ) -> None:
        super().__init__(parent)
        self.interval_ms = interval_ms
        self.stall_ms = stall_ms
        self.report_ms = report_ms
        self._tick_timer = QTimer(self)
        self._tick_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._tick_timer.setInterval(interval_ms)
        self._tick_timer.timeout.connect(self._on_tick)
        self._tick_clock = QElapsedTimer()
        self._report_clock = QElapsedTimer()
        self._reset_window()

    def _reset_window(self) -> None:
        self.stalls = 0
        self.severe_stalls = 0
        self.max_stall_ms = 0
        self.total_stall_ms = 0
        self.console_messages = 0
        self.presented_frames: dict[str, int] = {}

    def start(self) -> None:
        self._reset_window()
        self._tick_clock.start()
        self._report_clock.start()
        self._tick_timer.start()

    def stop(self) -> None:
        self._tick_timer.stop()

    def record_console_message(self) -> None:
        self.console_messages += 1

    def eventFilter(self, obj, event) -> bool:
        # Each Paint on a WebView's render widget is one frame reaching the screen.
        if event.type() == QEvent.Type.Paint:
            name = obj.property("uiPerfName") or "webview"
            self.presented_frames[name] = self.presented_frames.get(name, 0) + 1
        return False

    def record_tick(self, elapsed_ms: int) -> None:
        lateness = max(0, elapsed_ms - self.interval_ms)
        if lateness >= self.stall_ms:
            self.stalls += 1
            self.total_stall_ms += lateness
            if lateness >= self.stall_ms * 2:
                self.severe_stalls += 1
        self.max_stall_ms = max(self.max_stall_ms, lateness)

    def summary(self) -> str:
        return (
            f"stalls>={self.stall_ms}ms={self.stalls} "
            f"stalls>={self.stall_ms * 2}ms={self.severe_stalls} "
            f"max_stall={self.max_stall_ms}ms blocked_total={self.total_stall_ms}ms "
            f"js_console_forwarded={self.console_messages}"
            + "".join(f" frames[{name}]={count}" for name, count in sorted(self.presented_frames.items()))
        )

    def _on_tick(self) -> None:
        self.record_tick(self._tick_clock.restart())
        if self._report_clock.elapsed() >= self.report_ms:
            seconds = self._report_clock.restart() / 1000
            logger.info("[UI perf] %.1fs: %s", seconds, self.summary())
            self._reset_window()


_monitor: MainThreadStallMonitor | None = None


def install_if_enabled(parent: QObject | None = None) -> MainThreadStallMonitor | None:
    global _monitor
    if _monitor is None and perf_enabled():
        try:
            report_ms = max(1000, int(os.environ.get(REPORT_MS_ENV, "10000")))
        except ValueError:
            report_ms = 10_000
        _monitor = MainThreadStallMonitor(parent, report_ms=report_ms)
        _monitor.start()
        logger.info("[UI perf] Main-thread stall monitor enabled")
    return _monitor


def record_console_message() -> None:
    if _monitor is not None:
        _monitor.record_console_message()


def track_presented_frames(widget: QObject | None, name: str) -> None:
    if _monitor is not None and widget is not None:
        widget.setProperty("uiPerfName", name)
        widget.installEventFilter(_monitor)
