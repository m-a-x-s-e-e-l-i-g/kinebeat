from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from kinebeat.domain import EventKind, MusicalEvent, MusicAnalysis, SongMetadata


class MusicTimeline(QWidget):
    seekRequested = Signal(float)

    lane_order = (
        EventKind.KICK,
        EventKind.SNARE,
        EventKind.HI_HAT,
        EventKind.BASS,
        EventKind.VOCAL,
    )
    lane_labels = {
        EventKind.KICK: "KICK",
        EventKind.SNARE: "SNARE",
        EventKind.HI_HAT: "HI-HAT",
        EventKind.BASS: "BASS",
        EventKind.VOCAL: "VOCAL",
    }
    lane_colors = {
        EventKind.KICK: QColor("#e8b79c"),
        EventKind.SNARE: QColor("#d7c779"),
        EventKind.HI_HAT: QColor("#b8cfca"),
        EventKind.BASS: QColor("#bdadc9"),
        EventKind.VOCAL: QColor("#a9bbd1"),
    }

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("musicTimeline")
        self.setMinimumHeight(230)
        self._song: SongMetadata | None = None
        self._events: tuple[MusicalEvent, ...] = ()
        self._position_seconds = 0.0

    @property
    def position_seconds(self) -> float:
        return self._position_seconds

    def set_song(self, song: SongMetadata | None) -> None:
        self._song = song
        self._events = ()
        self._position_seconds = 0.0
        self.update()

    def set_analysis(self, analysis: MusicAnalysis | None) -> None:
        self._song = analysis.song if analysis else self._song
        self._events = analysis.events if analysis else ()
        self.update()

    def set_position(self, seconds: float) -> None:
        duration = self._song.duration_seconds if self._song else 0.0
        self._position_seconds = max(0.0, min(float(seconds), duration))
        self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._song or self._song.duration_seconds <= 0:
            return
        position = event.position()
        content_left = 76.0
        content_width = max(1.0, self.width() - content_left - 12.0)
        if position.x() < content_left or position.x() > content_left + content_width:
            return
        ratio = (position.x() - content_left) / content_width
        seconds = ratio * self._song.duration_seconds
        self.set_position(seconds)
        self.seekRequested.emit(seconds)

    def paintEvent(self, event: object) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0d0e0d"))
        label_width = 76
        top = 12
        waveform_height = 62
        content = QRectF(label_width, top, self.width() - label_width - 12, waveform_height)
        self._paint_grid(painter, content)
        self._paint_waveform(painter, content)
        lane_top = top + waveform_height + 12
        lane_height = max(24.0, (self.height() - lane_top - 10) / len(self.lane_order))
        for index, kind in enumerate(self.lane_order):
            lane = QRectF(
                label_width,
                lane_top + index * lane_height,
                self.width() - label_width - 12,
                lane_height,
            )
            self._paint_lane(painter, kind, lane)
        self._paint_playhead(painter, content)

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#292b29"), 1))
        for index in range(17):
            x = rect.left() + rect.width() * index / 16
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, self.height() - 10))
        painter.setPen(QColor("#696d69"))
        painter.setFont(QFont("Bahnschrift", 8))
        painter.drawText(QRectF(12, rect.top(), 52, 20), Qt.AlignmentFlag.AlignLeft, "SONG")

    def _paint_waveform(self, painter: QPainter, rect: QRectF) -> None:
        if not self._song or not self._song.waveform_peaks:
            painter.setPen(QColor("#636763"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "LOAD MUSIC TO BUILD THE TIMELINE")
            return
        peaks = self._song.waveform_peaks
        center = rect.center().y()
        path = QPainterPath(QPointF(rect.left(), center))
        for index, peak in enumerate(peaks):
            x = rect.left() + rect.width() * index / max(1, len(peaks) - 1)
            amplitude = peak * (rect.height() * 0.44)
            path.lineTo(x, center - amplitude)
        for index in range(len(peaks) - 1, -1, -1):
            x = rect.left() + rect.width() * index / max(1, len(peaks) - 1)
            amplitude = peaks[index] * (rect.height() * 0.44)
            path.lineTo(x, center + amplitude)
        path.closeSubpath()
        painter.fillPath(path, QColor("#d7d9d4"))

    def _paint_lane(self, painter: QPainter, kind: EventKind, rect: QRectF) -> None:
        painter.setPen(QPen(QColor("#252725"), 1))
        painter.drawLine(rect.topLeft(), rect.topRight())
        painter.setPen(QColor("#747974"))
        painter.setFont(QFont("Bahnschrift", 8, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(12, rect.top(), 56, rect.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self.lane_labels[kind],
        )
        duration = self._song.duration_seconds if self._song else 0
        if duration <= 0:
            return
        for musical_event in self._events:
            if musical_event.kind is not kind:
                continue
            x = rect.left() + rect.width() * min(1, musical_event.timestamp_seconds / duration)
            self._paint_event_marker(painter, kind, QPointF(x, rect.center().y()), musical_event)

    def _paint_event_marker(
        self,
        painter: QPainter,
        kind: EventKind,
        point: QPointF,
        event: MusicalEvent,
    ) -> None:
        color = self.lane_colors[kind]
        color.setAlphaF(0.45 + event.confidence * 0.55)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = 3.0 + event.confidence * 2.0
        if kind is EventKind.KICK:
            painter.drawEllipse(point, radius, radius)
        elif kind is EventKind.SNARE:
            painter.drawRect(QRectF(point.x() - radius, point.y() - radius, radius * 2, radius * 2))
        elif kind is EventKind.HI_HAT:
            painter.drawPolygon(
                QPolygonF(
                    [
                        QPointF(point.x(), point.y() - radius - 1),
                        QPointF(point.x() - radius, point.y() + radius),
                        QPointF(point.x() + radius, point.y() + radius),
                    ]
                )
            )
        else:
            painter.drawRoundedRect(QRectF(point.x() - 2, point.y() - radius, 4, radius * 2), 2, 2)

    def _paint_playhead(self, painter: QPainter, content: QRectF) -> None:
        if not self._song or self._song.duration_seconds <= 0:
            return
        ratio = self._position_seconds / self._song.duration_seconds
        x = content.left() + content.width() * ratio
        painter.setPen(QPen(QColor("#f2f4ee"), 1.5))
        painter.drawLine(QPointF(x, content.top()), QPointF(x, self.height() - 8))
        painter.setBrush(QColor("#f2f4ee"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(x - 5, content.top()),
                    QPointF(x + 5, content.top()),
                    QPointF(x, content.top() + 7),
                ]
            )
        )
