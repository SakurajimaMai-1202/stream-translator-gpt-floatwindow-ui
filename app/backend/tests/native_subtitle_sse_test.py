import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from native_subtitle import NativeSubtitleWindow
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
