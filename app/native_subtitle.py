"""不依賴 Chromium 的原生 Qt 浮動字幕視窗。"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from PyQt6.QtCore import QDateTime, QPoint, QRect, QTimer, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPainter, QPainterPath
from PyQt6.QtWidgets import QApplication, QWidget

from subtitle_history import entries_fitting_height, find_subtitle_index


logger = logging.getLogger(__name__)


class NativeSubtitleWindow(QWidget):
    """以 QPainter 繪製字幕，避開透明 QWebEngineView 的合成路徑。"""

    def __init__(
        self,
        config_manager=None,
        on_open_settings: Callable[[], None] | None = None,
        on_stop_translation: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.config_manager = config_manager
        self.on_open_settings = on_open_settings
        self.on_stop_translation = on_stop_translation
        self._lines: list[dict[str, Any]] = []
        self._task_id: str | None = None
        self._history_offset = 0
        self._is_recording = False
        self._drag_offset: QPoint | None = None
        self._resize_edge = 0
        self._resize_start_global: QPoint | None = None
        self._resize_start_geometry: QRect | None = None
        self._edge_margin = 8
        self._geometry_ready = False
        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(250)
        self._geometry_save_timer.timeout.connect(self._save_geometry)
        self._typing_timer = QTimer(self)
        self._typing_timer.setInterval(32)
        self._typing_timer.timeout.connect(self._advance_typing)

        self.settings: dict[str, Any] = {
            "fontSize": 24,
            "fontWeight": 700,
            "showOriginal": True,
            "showTranslated": True,
            "showTimestamp": False,
            "showLatency": False,
            "position": "bottom",
            "autoScroll": True,
            "maxDisplayCount": 5,
            "textColor": "#FFFFFF",
            "translatedColor": "#FFDD00",
            "timestampColor": "#888888",
            "latencyColor": "#7DD3FC",
            "backgroundColor": "#000000",
            "backgroundOpacity": 50,
        }

        self.setWindowTitle("字幕")
        app = QApplication.instance()
        if app is not None and not app.windowIcon().isNull():
            self.setWindowIcon(app.windowIcon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setMinimumSize(240, 100)

        self._load_config()
        self._geometry_ready = True

    def _load_config(self) -> None:
        if not self.config_manager:
            self.resize(800, 200)
            return
        config = self.config_manager.get_config()
        self.settings.update(config.get("subtitle_settings", {}))
        geometry = config.get("ui", {}).get("windows", {}).get("floating_subtitle", {})
        self.resize(int(geometry.get("width", 800)), int(geometry.get("height", 200)))
        self.move(int(geometry.get("x", 100)), int(geometry.get("y", 100)))

    def update_subtitle_json(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            logger.warning("原生字幕收到無效 JSON")
            return
        index = find_subtitle_index(self._lines, data)
        if index >= 0:
            previous = self._lines[index]
            data["_received_at_ms"] = previous.get(
                "_received_at_ms", QDateTime.currentMSecsSinceEpoch()
            )
            data["_display_original"] = self._reconcile_display(
                str(previous.get("_display_original", "")), str(data.get("original", ""))
            )
            data["_display_translated"] = self._reconcile_display(
                str(previous.get("_display_translated", "")), str(data.get("translated", ""))
            )
            self._lines[index] = data
        else:
            data["_received_at_ms"] = QDateTime.currentMSecsSinceEpoch()
            data["_display_original"] = ""
            data["_display_translated"] = ""
            self._lines.append(data)
        history_limit = max(100, int(self.settings.get("maxDisplayCount", 5)) * 3)
        self._lines = self._lines[-history_limit:]
        if self.settings.get("autoScroll", True):
            self._history_offset = 0
        if self._has_pending_typing():
            self._typing_timer.start()
        self.update()

    def begin_task(self, task_id: str) -> None:
        """Clear history only when translation switches to a genuinely new task."""
        task_id = str(task_id)
        if self._task_id == task_id:
            return
        self._task_id = task_id
        self._typing_timer.stop()
        self._lines.clear()
        self._history_offset = 0
        self.update()

    @staticmethod
    def _reconcile_display(rendered: str, target: str) -> str:
        """保留仍相同的前綴，避免串流內容修訂時整句閃爍。"""
        prefix_length = 0
        for old_char, new_char in zip(rendered, target):
            if old_char != new_char:
                break
            prefix_length += 1
        return target[:prefix_length]

    def _has_pending_typing(self) -> bool:
        return any(
            str(line.get(f"_display_{field}", "")) != str(line.get(field, ""))
            for line in self._lines
            for field in ("original", "translated")
        )

    def _advance_typing(self) -> None:
        changed = False
        for line in self._lines:
            for field in ("original", "translated"):
                target = str(line.get(field, ""))
                display_key = f"_display_{field}"
                rendered = str(line.get(display_key, ""))
                if len(rendered) < len(target):
                    # 長句每格多顯示一些字，仍保有清楚的流動感且不拖慢字幕。
                    step = max(1, (len(target) + 89) // 90)
                    line[display_key] = target[:len(rendered) + step]
                    changed = True
        if changed:
            self.update()
        if not self._has_pending_typing():
            self._typing_timer.stop()

    def update_settings_json(self, payload: str) -> None:
        try:
            self.settings.update(json.loads(payload))
            self._history_offset = min(self._history_offset, self._max_history_offset())
            self.update()
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("原生字幕收到無效設定 JSON")

    def update_recording_state(self, is_recording: bool) -> None:
        self._is_recording = bool(is_recording)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        opacity = max(0, min(100, int(self.settings.get("backgroundOpacity", 50))))
        background = QColor(str(self.settings.get("backgroundColor", "#000000")))
        background.setAlpha(round(opacity * 2.55))
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        painter.fillPath(path, background)

        # 綠色代表正在收音／翻譯；紅色代表尚未啟動或已停止。
        indicator_color = QColor("#22C55E" if self._is_recording else "#EF4444")
        painter.setPen(QColor(255, 255, 255, 90))
        painter.setBrush(indicator_color)
        indicator_size = 11
        indicator_x = self.width() - 25 - indicator_size // 2
        indicator_y = 8
        painter.drawEllipse(indicator_x, indicator_y, indicator_size, indicator_size)

        font_size = max(10, int(self.settings.get("fontSize", 24)))
        font_weight = max(100, min(900, int(self.settings.get("fontWeight", 700))))
        text_font = QFont("Microsoft JhengHei UI")
        text_font.setPixelSize(font_size)
        text_font.setWeight(QFont.Weight(font_weight))
        metadata_font = QFont(text_font)
        metadata_font.setPixelSize(max(10, round(font_size * 0.48)))

        margin = 16
        content_width = max(80, self.width() - margin * 2 - 42)
        entries = self._layout_entries(text_font, metadata_font, content_width)
        # entry.height 已包含每筆尾端間距；分隔線畫在該間距內，不可再次
        # 累加，否則會誤判溢出並造成頂部裁切、底部留白過多。
        available_height = max(0, self.height() - margin * 2)
        entries = entries_fitting_height(entries, available_height)
        total_height = sum(entry["height"] for entry in entries)
        if total_height > available_height:
            # 內容超出視窗時由底部往上溢出，確保最新字幕永遠可見。
            y = self.height() - margin - total_height
        elif self.settings.get("position") == "top":
            y = margin
        else:
            y = self.height() - margin - total_height

        for index, entry in enumerate(entries):
            if index:
                painter.setPen(QColor(255, 255, 255, 28))
                painter.drawLine(margin, y - 5, self.width() - margin, y - 5)
            metadata = entry["metadata"]
            if metadata:
                painter.setFont(metadata_font)
                painter.setPen(QColor(str(self.settings.get("latencyColor", "#7DD3FC"))))
                painter.drawText(QRect(margin, y, content_width, entry["metadata_height"]), Qt.TextFlag.TextWordWrap, metadata)
                y += entry["metadata_height"] + 4
            for text, color, height in entry["rows"]:
                bar_rect = QRect(margin, y + 2, 4, max(8, height - 4))
                painter.fillRect(bar_rect, color)
                text_rect = QRect(margin + 10, y, content_width - 10, height)
                painter.setFont(text_font)
                painter.setPen(QColor(0, 0, 0, 220))
                painter.drawText(text_rect.translated(2, 2), Qt.TextFlag.TextWordWrap, text)
                painter.setPen(color)
                painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, text)
                y += height + 4
            y += 6

        self._paint_controls(painter)

    def _layout_entries(self, text_font: QFont, metadata_font: QFont, width: int) -> list[dict[str, Any]]:
        text_metrics = QFontMetrics(text_font)
        metadata_metrics = QFontMetrics(metadata_font)
        entries: list[dict[str, Any]] = []
        limit = max(1, int(self.settings.get("maxDisplayCount", 5)))
        end = max(0, len(self._lines) - self._history_offset)
        start = max(0, end - limit)
        for line in self._lines[start:end]:
            metadata = self._metadata_text(line)
            metadata_height = metadata_metrics.boundingRect(
                QRect(0, 0, width, 1000), Qt.TextFlag.TextWordWrap, metadata
            ).height() if metadata else 0
            rows: list[tuple[str, QColor, int]] = []
            if self.settings.get("showOriginal", True) and line.get("original"):
                text = str(line.get("_display_original", line["original"]))
                height = max(text_metrics.height(), text_metrics.boundingRect(QRect(0, 0, width - 10, 4000), Qt.TextFlag.TextWordWrap, text).height())
                rows.append((text, QColor(str(self.settings.get("textColor", "#FFFFFF"))), height))
            if self.settings.get("showTranslated", True) and line.get("translated"):
                text = str(line.get("_display_translated", line["translated"]))
                height = max(text_metrics.height(), text_metrics.boundingRect(QRect(0, 0, width - 10, 4000), Qt.TextFlag.TextWordWrap, text).height())
                rows.append((text, QColor(str(self.settings.get("translatedColor", "#FFDD00"))), height))
            entries.append({
                "metadata": metadata,
                "metadata_height": metadata_height,
                "rows": rows,
                "height": metadata_height + (4 if metadata else 0) + sum(row[2] + 4 for row in rows) + 6,
            })
        return entries

    def _metadata_text(self, line: dict[str, Any]) -> str:
        parts: list[str] = []
        if self.settings.get("showTimestamp", False):
            received_at = line.get("_received_at_ms")
            if isinstance(received_at, (int, float)):
                parts.append(QDateTime.fromMSecsSinceEpoch(int(received_at)).toString("HH:mm"))
        if self.settings.get("showLatency", False):
            latency_fields = (
                ("ASR", "asr_latency_ms"),
                ("排隊", "translation_queue_latency_ms"),
                ("翻譯", "llm_latency_ms"),
                ("總計", "total_latency_ms"),
            )
            for label, field in latency_fields:
                value = line.get(field)
                if isinstance(value, (int, float)):
                    formatted = f"{value / 1000:.2f}s" if value >= 1000 else f"{round(value)}ms"
                    parts.append(f"{label} {formatted}")
        return " · ".join(parts)

    def _paint_controls(self, painter: QPainter) -> None:
        painter.setPen(QColor(255, 255, 255, 185))
        control_font = QFont("Segoe UI Symbol")
        control_font.setPixelSize(18)
        painter.setFont(control_font)
        controls = (
            (self._settings_rect(), "⚙"),
            (self._stop_rect(), "■"),
            (self._clear_rect(), "⌫"),
            (self._close_rect(), "×"),
        )
        for rect, symbol in controls:
            painter.setBrush(QColor(0, 0, 0, 105))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(rect)
            painter.setPen(QColor(255, 255, 255, 205))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, symbol)

    def _settings_rect(self) -> QRect:
        return QRect(self.width() - 42, 28, 34, 30)

    def _close_rect(self) -> QRect:
        return QRect(self.width() - 42, 136, 32, 32)

    def _stop_rect(self) -> QRect:
        return QRect(self.width() - 42, 64, 32, 32)

    def _clear_rect(self) -> QRect:
        return QRect(self.width() - 42, 100, 32, 32)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            local_pos = event.position().toPoint()
            if self._settings_rect().contains(local_pos):
                if callable(self.on_open_settings):
                    self.on_open_settings()
                event.accept()
                return
            if self._close_rect().contains(local_pos):
                self.close()
                event.accept()
                return
            if self._stop_rect().contains(local_pos):
                if callable(self.on_stop_translation):
                    self.on_stop_translation()
                event.accept()
                return
            if self._clear_rect().contains(local_pos):
                self._typing_timer.stop()
                self._lines.clear()
                self._history_offset = 0
                self.update()
                event.accept()
                return
            edge = self._edge_at(local_pos)
            if edge:
                self._resize_edge = edge
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geometry = self.geometry()
                event.accept()
                return
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._resize_edge and self._resize_start_global is not None and self._resize_start_geometry is not None:
            self._resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        self._update_resize_cursor(self._edge_at(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
        self._resize_edge = 0
        self._resize_start_global = None
        self._resize_start_geometry = None
        self.unsetCursor()
        self._schedule_geometry_save()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if callable(self.on_open_settings):
            self.on_open_settings()
        event.accept()

    def wheelEvent(self, event) -> None:
        if not self._lines:
            return
        step = 1 if event.angleDelta().y() > 0 else -1
        self._history_offset = max(0, min(self._max_history_offset(), self._history_offset + step))
        self.update()
        event.accept()

    def _max_history_offset(self) -> int:
        limit = max(1, int(self.settings.get("maxDisplayCount", 5)))
        return max(0, len(self._lines) - limit)

    def _edge_at(self, point: QPoint) -> int:
        edge = 0
        if point.x() <= self._edge_margin:
            edge |= 1
        elif point.x() >= self.width() - self._edge_margin:
            edge |= 2
        if point.y() <= self._edge_margin:
            edge |= 4
        elif point.y() >= self.height() - self._edge_margin:
            edge |= 8
        return edge

    def _update_resize_cursor(self, edge: int) -> None:
        cursors = {
            1: Qt.CursorShape.SizeHorCursor,
            2: Qt.CursorShape.SizeHorCursor,
            4: Qt.CursorShape.SizeVerCursor,
            8: Qt.CursorShape.SizeVerCursor,
            5: Qt.CursorShape.SizeFDiagCursor,
            10: Qt.CursorShape.SizeFDiagCursor,
            6: Qt.CursorShape.SizeBDiagCursor,
            9: Qt.CursorShape.SizeBDiagCursor,
        }
        cursor = cursors.get(edge, Qt.CursorShape.ArrowCursor)
        if self.cursor().shape() != cursor:
            self.setCursor(cursor)

    def _resize_to(self, global_pos: QPoint) -> None:
        assert self._resize_start_global is not None
        assert self._resize_start_geometry is not None
        delta = global_pos - self._resize_start_global
        rect = QRect(self._resize_start_geometry)
        if self._resize_edge & 1:
            rect.setLeft(min(rect.right() - self.minimumWidth(), rect.left() + delta.x()))
        if self._resize_edge & 2:
            rect.setRight(max(rect.left() + self.minimumWidth(), rect.right() + delta.x()))
        if self._resize_edge & 4:
            rect.setTop(min(rect.bottom() - self.minimumHeight(), rect.top() + delta.y()))
        if self._resize_edge & 8:
            rect.setBottom(max(rect.top() + self.minimumHeight(), rect.bottom() + delta.y()))
        self.setGeometry(rect)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def _schedule_geometry_save(self) -> None:
        if self._geometry_ready and self.config_manager:
            self._geometry_save_timer.start()

    def _save_geometry(self) -> None:
        if not self.config_manager:
            return
        geometry = self.geometry()
        self.config_manager.save_window_state("floating_subtitle", {
            "x": geometry.x(),
            "y": geometry.y(),
            "width": geometry.width(),
            "height": geometry.height(),
        })
