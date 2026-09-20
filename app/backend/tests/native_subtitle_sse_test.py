import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFont
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from native_subtitle import (
    CONTENT_MARGIN,
    MIN_WINDOW_HEIGHT,
    NativeSubtitleWindow,
    complete_partial_entry_height,
    entries_filling_viewport,
    subtitle_content_origin,
    visible_entries_height,
)
from sse_parser import SseEventParser
from subtitle_history import entries_fitting_height, find_subtitle_index, subtitle_identity


class _LegacySubtitleConfig:
    def get_config(self):
        return {
            "subtitle_settings": {
                "maxDisplayCount": 5,
                "showTimestamp": False,
                "showLatency": False,
            },
            "ui": {
                "windows": {
                    "floating_subtitle": {
                        "x": 100,
                        "y": 100,
                        "width": 800,
                        "height": 200,
                    }
                }
            },
        }


def test_parser_handles_utf8_split_across_chunks():
    parser = SseEventParser()
    payload = 'event: subtitle\ndata: {"original":"日本語","translated":"中文"}\n\n'.encode("utf-8")
    split_at = payload.index("日".encode("utf-8")) + 1

    assert parser.feed(payload[:split_at]) == []
    assert parser.feed(payload[split_at:]) == [
        ("subtitle", '{"original":"日本語","translated":"中文"}')
    ]


def test_parser_ignores_ping_and_joins_multiline_data():
    parser = SseEventParser()

    assert parser.feed(b": ping\n\nevent: subtitle\ndata: first\ndata: second\n\n") == [
        ("subtitle", "first\nsecond")
    ]


def test_parser_accepts_crlf_chunks():
    parser = SseEventParser()

    assert parser.feed(b"event: status\r\ndata: {\"status\":\"running\"}\r\n\r\n") == [
        ("status", '{"status":"running"}')
    ]


def test_parser_handles_crlf_delimiter_split_between_chunks():
    parser = SseEventParser()

    assert parser.feed(b"event: subtitle\r\ndata: {}\r") == []
    assert parser.feed(b"\n\r\n") == [("subtitle", "{}")]


def test_subtitle_identity_prefers_segment_then_backend_timestamp():
    assert subtitle_identity({"segment_id": 7, "timestamp": "00:01"}) == ("segment", "7")
    assert subtitle_identity({"backend_timestamp": "00:01", "id": "local"}) == ("timestamp", "00:01")
    assert subtitle_identity({"timestamp": "00:02"}) == ("timestamp", "00:02")
    assert subtitle_identity({"id": "local"}) == ("id", "local")
    assert subtitle_identity({}) is None


def test_viewport_keeps_multiple_newest_entries_that_fit():
    entries = [{"id": 1, "height": 40}, {"id": 2, "height": 40}, {"id": 3, "height": 40}]

    assert entries_fitting_height(entries, 85) == entries[1:]
    assert entries_fitting_height(entries, 20) == entries[-1:]


def test_visible_height_excludes_only_the_final_following_row_gap():
    entries = [{"height": 40}, {"height": 50}]

    assert visible_entries_height(entries) == 84
    assert visible_entries_height([]) == 0


def test_top_and_bottom_alignment_use_the_same_visible_edge_margin():
    window_height = 240
    entries = [{"height": 40}, {"height": 50}]
    visible_height = visible_entries_height(entries)
    top_origin = CONTENT_MARGIN
    bottom_origin = window_height - CONTENT_MARGIN - visible_height

    assert top_origin == CONTENT_MARGIN
    assert window_height - (bottom_origin + visible_height) == CONTENT_MARGIN


def test_scrolling_history_keeps_only_a_small_bottom_gap():
    entries = [{"height": 90}, {"height": 90}]
    origin = subtitle_content_origin(MIN_WINDOW_HEIGHT, entries, overflowed=True)

    assert MIN_WINDOW_HEIGHT - (origin + visible_entries_height(entries)) == CONTENT_MARGIN


def test_unfilled_history_starts_after_the_top_gap():
    entries = [{"height": 70}, {"height": 70}]

    assert subtitle_content_origin(MIN_WINDOW_HEIGHT, entries, overflowed=False) == CONTENT_MARGIN


def test_viewport_uses_spare_height_for_the_previous_subtitle_top():
    entries = [
        {"id": 1, "height": 90, "metadata": "01:32", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
        {"id": 2, "height": 90, "metadata": "01:33", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
        {"id": 3, "height": 90, "metadata": "01:33", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
    ]

    visible, overflowed = entries_filling_viewport(entries, available_height=230, minimum_partial_height=30)

    assert overflowed is True
    assert [entry["id"] for entry in visible] == [1, 2, 3]
    assert visible[0]["partial_height"] == 50
    assert visible[0]["partial_slot_height"] == 56
    assert "partial_height" not in visible[1]


def test_viewport_does_not_show_an_unreadable_partial_sliver():
    entries = [
        {"id": 1, "height": 90, "metadata": "01:32", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
        {"id": 2, "height": 90, "metadata": "01:33", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
        {"id": 3, "height": 90, "metadata": "01:33", "metadata_height": 12, "rows": [("original", None, 30), ("translated", None, 30)]},
    ]

    visible, overflowed = entries_filling_viewport(entries, available_height=190, minimum_partial_height=30)

    assert overflowed is True
    assert [entry["id"] for entry in visible] == [2, 3]


def test_partial_preview_never_clips_through_a_translation_row():
    entry = {
        "metadata": "01:32 · ASR 61ms",
        "metadata_height": 12,
        "rows": [("original", None, 30), ("translated", None, 30)],
    }

    assert complete_partial_entry_height(entry, available_height=65) == 50
    assert complete_partial_entry_height(entry, available_height=84) == 84


def test_native_subtitle_clamps_legacy_package_height_and_keeps_history():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(_LegacySubtitleConfig())
    try:
        assert window.height() == 240
        for segment_id in range(1, 4):
            window.update_subtitle_json(json.dumps({
                "segment_id": segment_id,
                "original": f"original {segment_id}",
                "translated": f"translated {segment_id}",
            }))

        assert len(window._lines) == 3
        font = QFont("Microsoft JhengHei UI")
        font.setPixelSize(24)
        metadata_font = QFont(font)
        metadata_font.setPixelSize(12)
        entries = window._layout_entries(font, metadata_font, 726)
        visible = entries_fitting_height(entries, window.height() - 32)
        assert len(visible) >= 2
        assert window._flow_active is True
    finally:
        window.close()
        app.processEvents()


def test_minimum_window_height_keeps_two_complete_subtitles_at_smallest_font():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(_LegacySubtitleConfig())
    try:
        window.settings.update({
            "fontSize": 16,
            "showTimestamp": True,
            "showLatency": True,
            "maxDisplayCount": 5,
        })
        for segment_id in range(1, 4):
            window.update_subtitle_json(json.dumps({
                "segment_id": segment_id,
                "original": f"original {segment_id}",
                "translated": f"translated {segment_id}",
                "asr_latency_ms": 63,
                "total_latency_ms": 375,
            }))

        font = QFont("Microsoft JhengHei UI")
        font.setPixelSize(16)
        metadata_font = QFont(font)
        metadata_font.setPixelSize(10)
        entries = window._layout_entries(font, metadata_font, 726)
        visible = entries_fitting_height(
            entries,
            MIN_WINDOW_HEIGHT - CONTENT_MARGIN * 2 + 6,
        )

        assert len(visible) >= 2
    finally:
        window.close()
        app.processEvents()


def test_native_subtitle_keeps_timestamp_and_latency_as_separate_color_runs():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(_LegacySubtitleConfig())
    try:
        window.settings.update({"showTimestamp": True, "showLatency": True})
        line = {
            "_received_at_ms": 1_700_000_000_000,
            "asr_latency_ms": 63,
            "translation_queue_latency_ms": 1,
            "llm_latency_ms": 483,
            "total_latency_ms": 762,
            "original": "日本語",
            "translated": "中文",
        }

        timestamp, latency = window._metadata_parts(line)

        assert timestamp
        assert latency == "ASR 63ms · 排隊 1ms · 翻譯 483ms · 總計 762ms"

        font = QFont("Microsoft JhengHei UI")
        font.setPixelSize(24)
        metadata_font = QFont(font)
        metadata_font.setPixelSize(12)
        entry = window._layout_line(line, font, metadata_font, 726, 0)
        assert entry["metadata_timestamp"] == timestamp
        assert entry["metadata_latency"] == latency
        assert entry["metadata_timestamp_width"] > 0
    finally:
        window.close()
        app.processEvents()


def test_native_subtitle_flow_only_restarts_for_a_new_row():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(_LegacySubtitleConfig())
    try:
        window.update_subtitle_json(json.dumps({
            "segment_id": 1,
            "original": "first",
            "translated": "第一句",
        }))
        assert window._flow_active is True
        window._flow_timer.stop()
        window._flow_active = False

        window.update_subtitle_json(json.dumps({
            "segment_id": 1,
            "original": "first updated",
            "translated": "第一句更新",
        }))
        assert window._flow_active is False

        window.update_subtitle_json(json.dumps({
            "segment_id": 2,
            "original": "second",
            "translated": "第二句",
        }))
        assert window._flow_active is True
        assert window._flow_timer.isActive()
        assert 0.0 <= window._flow_progress() <= 1.0
    finally:
        window.close()
        app.processEvents()


def test_native_subtitle_flow_progresses_and_finishes():
    app = QApplication.instance() or QApplication([])
    window = NativeSubtitleWindow(_LegacySubtitleConfig())
    window.settings["maxDisplayCount"] = 3
    try:
        for segment_id in range(1, 4):
            window.update_subtitle_json(json.dumps({
                "segment_id": segment_id,
                "original": f"original {segment_id}",
                "translated": f"translated {segment_id}",
            }))
        start_progress = window._flow_progress()
        QTest.qWait(110)
        middle_progress = window._flow_progress()
        QTest.qWait(240)

        assert 0.0 <= start_progress < middle_progress < 1.0
        assert window._flow_active is False
    finally:
        window.close()
        app.processEvents()


def test_final_segment_matches_earlier_timestamp_only_subtitle():
    lines = [
        {
            "timestamp": "00:01:11,360 -> 00:01:13,888",
            "original": "ございます、うん。",
            "translated": "",
        }
    ]
    final = {
        "segment_id": 12,
        "timestamp": "00:01:11,360 -> 00:01:13,888",
        "original": "ございます、うん。",
        "translated": "是的，嗯。",
    }

    assert find_subtitle_index(lines, final) == 0


def test_segment_id_still_wins_when_timestamp_is_reformatted():
    lines = [{"segment_id": 12, "timestamp": "old timestamp"}]

    assert find_subtitle_index(lines, {"segment_id": "12", "timestamp": "new timestamp"}) == 0
