import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui_perf import MainThreadStallMonitor


def test_stall_monitor_counts_only_lateness_beyond_the_interval():
    app = QApplication.instance() or QApplication([])
    monitor = MainThreadStallMonitor(app, interval_ms=10, stall_ms=50)

    monitor.record_tick(10)
    monitor.record_tick(59)
    monitor.record_tick(60)
    monitor.record_tick(115)

    assert monitor.stalls == 2
    assert monitor.severe_stalls == 1
    assert monitor.max_stall_ms == 105
    assert monitor.total_stall_ms == 155


def test_stall_summary_reports_presented_frames_per_window():
    app = QApplication.instance() or QApplication([])
    monitor = MainThreadStallMonitor(app)
    monitor.record_console_message()
    monitor.presented_frames["Stream Translator"] = 58

    summary = monitor.summary()

    assert "js_console_forwarded=1" in summary
    assert "frames[Stream Translator]=58" in summary
