from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths, Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from kinebeat.domain import EventKind, MusicalEvent, MusicAnalysis, SongMetadata, StemArtifact
from kinebeat.processing import MusicAnalysisService, probe_song
from kinebeat.ui.tasks import TaskWorker
from kinebeat.ui.timeline import MusicTimeline

AUDIO_FILTER = "Music files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus);;All files (*.*)"


class MusicDropZone(QFrame):
    musicSelected = Signal(Path)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("dropZone")
        self.setProperty("dragActive", False)
        self.setAcceptDrops(True)
        self.setMinimumHeight(104)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(4)
        title = QLabel("DROP A SONG HERE")
        title.setObjectName("dropTitle")
        hint = QLabel("WAV, MP3, FLAC, M4A, AAC, OGG")
        hint.setObjectName("dropHint")
        layout.addStretch()
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def dragEnterEvent(self, event: Any) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            event.acceptProposedAction()
            self._set_drag_active(True)

    def dragLeaveEvent(self, event: Any) -> None:  # noqa: ARG002
        self._set_drag_active(False)

    def dropEvent(self, event: Any) -> None:
        self._set_drag_active(False)
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.musicSelected.emit(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()

    def _set_drag_active(self, active: bool) -> None:
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)


class KinebeatWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Kinebeat")
        self.resize(1480, 900)
        self.setMinimumSize(1120, 720)
        self._song: SongMetadata | None = None
        self._analysis: MusicAnalysis | None = None
        self._task_thread: QThread | None = None
        self._task_worker: TaskWorker | None = None
        self._build_ui()
        self._sync_state()

    def _build_ui(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_header())
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)
        body.addWidget(self._build_setup_rail())
        body.addWidget(self._build_workspace())
        body.addWidget(self._build_inspector())
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([292, 900, 286])
        root_layout.addWidget(body, 1)
        root_layout.addWidget(self._build_task_bar())
        self.setCentralWidget(root)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("appHeader")
        header.setFixedHeight(64)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)
        wordmark = QLabel("KINEBEAT")
        wordmark.setObjectName("wordmark")
        strapline = QLabel("MUSIC BUILDS THE CUT")
        strapline.setObjectName("strapline")
        privacy = QLabel("LOCAL PROCESSING")
        privacy.setObjectName("privacyBadge")
        layout.addWidget(wordmark)
        layout.addWidget(strapline)
        layout.addStretch()
        layout.addWidget(privacy)
        return header

    def _build_setup_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("setupRail")
        rail.setMinimumWidth(260)
        rail.setMaximumWidth(360)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)
        music_section = QFrame()
        music_section.setObjectName("stepSection")
        music_layout = QVBoxLayout(music_section)
        music_layout.setContentsMargins(0, 0, 0, 18)
        music_layout.setSpacing(10)
        music_layout.addLayout(self._step_heading("01", "Music"))
        self.drop_zone = MusicDropZone()
        self.drop_zone.musicSelected.connect(self.load_song)
        self.song_name = QLabel("No song loaded")
        self.song_name.setObjectName("sourceName")
        self.song_name.setWordWrap(True)
        self.song_meta = QLabel("Your music stays on this computer.")
        self.song_meta.setObjectName("sourceMeta")
        self.song_meta.setWordWrap(True)
        self.choose_music_button = QPushButton("Choose music")
        self.choose_music_button.setObjectName("secondaryButton")
        self.choose_music_button.clicked.connect(self._choose_music)
        self.analyse_button = QPushButton("Analyse music")
        self.analyse_button.setObjectName("primaryButton")
        self.analyse_button.clicked.connect(self._analyse_music)
        music_layout.addWidget(self.drop_zone)
        music_layout.addWidget(self.song_name)
        music_layout.addWidget(self.song_meta)
        music_layout.addWidget(self.choose_music_button)
        music_layout.addWidget(self.analyse_button)
        footage_section = QFrame()
        footage_section.setObjectName("stepSection")
        footage_layout = QVBoxLayout(footage_section)
        footage_layout.setContentsMargins(0, 0, 0, 18)
        footage_layout.setSpacing(10)
        footage_layout.addLayout(self._step_heading("02", "Footage"))
        footage_copy = QLabel("Import clips after the musical structure is ready.")
        footage_copy.setObjectName("bodyMuted")
        footage_copy.setWordWrap(True)
        self.footage_button = QPushButton("Import video clips")
        self.footage_button.setObjectName("secondaryButton")
        footage_layout.addWidget(footage_copy)
        footage_layout.addWidget(self.footage_button)
        layout.addWidget(music_section)
        layout.addWidget(footage_section)
        layout.addStretch()
        return rail

    def _step_heading(self, number: str, title: str) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)
        number_label = QLabel(number)
        number_label.setObjectName("stepNumber")
        title_label = QLabel(title)
        title_label.setObjectName("sectionTitle")
        layout.addWidget(number_label)
        layout.addWidget(title_label)
        layout.addStretch()
        return layout

    def _build_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        preview = QFrame()
        preview.setObjectName("previewSurface")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(40, 30, 40, 30)
        preview_layout.addStretch()
        self.preview_eyebrow = QLabel("START WITH THE SOUND")
        self.preview_eyebrow.setObjectName("eyebrow")
        self.preview_title = QLabel("Your song sets\nthe timeline.")
        self.preview_title.setObjectName("previewTitle")
        self.preview_body = QLabel(
            "Kinebeat separates the instruments, finds their events, "
            "and builds an edit you can keep refining."
        )
        self.preview_body.setObjectName("previewBody")
        self.preview_body.setWordWrap(True)
        self.preview_body.setMaximumWidth(520)
        preview_layout.addWidget(self.preview_eyebrow)
        preview_layout.addWidget(self.preview_title)
        preview_layout.addSpacing(6)
        preview_layout.addWidget(self.preview_body)
        preview_layout.addStretch()
        timeline_header = QFrame()
        timeline_header.setObjectName("timelineHeader")
        timeline_header.setFixedHeight(48)
        timeline_header_layout = QHBoxLayout(timeline_header)
        timeline_header_layout.setContentsMargins(14, 0, 14, 0)
        timeline_title = QLabel("MUSICAL TIMELINE")
        timeline_title.setObjectName("timelineTitle")
        self.timeline_meta = QLabel("WAITING FOR MUSIC")
        self.timeline_meta.setObjectName("timelineMeta")
        timeline_header_layout.addWidget(timeline_title)
        timeline_header_layout.addStretch()
        timeline_header_layout.addWidget(self.timeline_meta)
        self.timeline = MusicTimeline()
        layout.addWidget(preview, 1)
        layout.addWidget(timeline_header)
        layout.addWidget(self.timeline)
        return workspace

    def _build_inspector(self) -> QFrame:
        inspector = QFrame()
        inspector.setObjectName("inspector")
        inspector.setMinimumWidth(250)
        inspector.setMaximumWidth(340)
        layout = QVBoxLayout(inspector)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(12)
        eyebrow = QLabel("GENERATOR")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("First-cut rules")
        title.setObjectName("sectionTitle")
        helper = QLabel("Mappings activate after music analysis.")
        helper.setObjectName("bodyMuted")
        helper.setWordWrap(True)
        strategy_label = QLabel("FOOTAGE SELECTION")
        strategy_label.setObjectName("fieldLabel")
        self.strategy_combo = QComboBox()
        self.strategy_combo.addItems(
            [
                "Movement based",
                "Import order",
                "Random",
                "Least used first",
                "Subject based",
                "Manual ranking",
            ]
        )
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addSpacing(12)
        layout.addWidget(strategy_label)
        layout.addWidget(self.strategy_combo)
        layout.addSpacing(12)
        for instrument, effect in (
            ("KICK", "CUT + RANDOM EFFECT"),
            ("SNARE", "CUT"),
            ("HI-HAT", "LIGHT EFFECT · 0.2 S"),
            ("BASS", "TIME BEND"),
            ("VOCAL", "NO ACTION"),
        ):
            layout.addWidget(self._mapping_row(instrument, effect))
        layout.addStretch()
        self.generate_button = QPushButton("Generate first cut")
        self.generate_button.setObjectName("primaryButton")
        layout.addWidget(self.generate_button)
        return inspector

    def _mapping_row(self, instrument: str, effect: str) -> QFrame:
        row = QFrame()
        row.setObjectName("mappingRow")
        row.setMinimumHeight(54)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)
        instrument_label = QLabel(instrument)
        instrument_label.setObjectName("mappingInstrument")
        effect_label = QLabel(effect)
        effect_label.setObjectName("mappingEffect")
        layout.addWidget(instrument_label)
        layout.addWidget(effect_label)
        return row

    def _build_task_bar(self) -> QFrame:
        self.task_bar = QFrame()
        self.task_bar.setObjectName("taskBar")
        self.task_bar.setFixedHeight(54)
        layout = QHBoxLayout(self.task_bar)
        layout.setContentsMargins(16, 7, 16, 7)
        layout.setSpacing(12)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        self.task_title = QLabel("READY")
        self.task_title.setObjectName("taskTitle")
        self.task_detail = QLabel("Load a song to begin")
        self.task_detail.setObjectName("taskDetail")
        text_layout.addWidget(self.task_title)
        text_layout.addWidget(self.task_detail)
        self.task_progress = QProgressBar()
        self.task_progress.setRange(0, 100)
        self.task_progress.setValue(0)
        self.task_progress.setTextVisible(False)
        self.task_progress.setFixedWidth(240)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("quietButton")
        self.cancel_button.clicked.connect(self._cancel_task)
        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(self.task_progress)
        layout.addWidget(self.cancel_button)
        return self.task_bar

    @Slot()
    def _choose_music(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose music", "", AUDIO_FILTER)
        if path:
            self.load_song(Path(path))

    @Slot(Path)
    def load_song(self, path: Path) -> None:
        self._start_task(
            title="IMPORTING MUSIC",
            task=lambda **kwargs: probe_song(path, **kwargs),
            on_success=self._song_loaded,
        )

    @Slot()
    def _analyse_music(self) -> None:
        if not self._song:
            return
        cache_location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        service = MusicAnalysisService(cache_root=Path(cache_location) / "analysis")
        self._start_task(
            title="ANALYSING MUSIC",
            task=lambda **kwargs: service.analyse(self._song, **kwargs),
            on_success=self._analysis_ready,
        )

    def _start_task(
        self,
        *,
        title: str,
        task: Callable[..., Any],
        on_success: Callable[[Any], None],
    ) -> None:
        if self._task_thread:
            return
        thread = QThread(self)
        worker = TaskWorker(task)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._task_progressed)
        worker.succeeded.connect(on_success)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._task_finished)
        self._task_thread = thread
        self._task_worker = worker
        self.task_title.setText(title)
        self.task_detail.setText("Preparing local processing")
        self.task_progress.setValue(0)
        self._sync_state()
        thread.start()

    @Slot(int, str)
    def _task_progressed(self, value: int, detail: str) -> None:
        self.task_progress.setValue(value)
        self.task_detail.setText(detail)

    @Slot(object)
    def _song_loaded(self, result: object) -> None:
        assert isinstance(result, SongMetadata)
        self._song = result
        self._analysis = None
        self.song_name.setText(result.path.name)
        self.song_meta.setText(
            f"{result.display_duration} · {result.sample_rate / 1000:.1f} kHz · "
            f"{result.channels} ch · {result.codec.upper()}"
        )
        self.preview_eyebrow.setText("MUSIC LOADED")
        self.preview_title.setText("Ready to find\nthe structure.")
        self.preview_body.setText(
            "Analysis separates drums, bass, vocals, guitar, piano, and other sound "
            "before finding timeline events."
        )
        self.timeline.set_song(result)
        self.timeline_meta.setText(f"{result.display_duration} · READY TO ANALYSE")

    @Slot(object)
    def _analysis_ready(self, result: object) -> None:
        assert isinstance(result, MusicAnalysis)
        self._analysis = result
        self.timeline.set_analysis(result)
        self.timeline_meta.setText(f"{len(result.events)} EVENTS · {result.model_name.upper()}")
        self.preview_eyebrow.setText("STRUCTURE READY")
        self.preview_title.setText("Now bring in\nthe footage.")
        self.preview_body.setText(
            "The detected events are ready for mappings, clip generation, "
            "locking, and regeneration."
        )

    @Slot(str)
    def _task_failed(self, message: str) -> None:
        self.task_title.setText("ANALYSIS NEEDS ATTENTION")
        self.task_detail.setText(message)
        QMessageBox.warning(self, "Kinebeat could not continue", message)

    @Slot()
    def _task_finished(self) -> None:
        self._task_thread = None
        self._task_worker = None
        if self._analysis:
            self.task_title.setText("STRUCTURE READY")
            self.task_detail.setText("Import footage to generate the first cut")
            self.task_progress.setValue(100)
        elif self._song:
            self.task_title.setText("MUSIC READY")
            self.task_detail.setText("Analyse the song to separate instruments")
            self.task_progress.setValue(0)
        self._sync_state()

    @Slot()
    def _cancel_task(self) -> None:
        if self._task_worker:
            self.task_detail.setText("Stopping after the current processing step")
            self._task_worker.cancel()

    def _sync_state(self) -> None:
        busy = self._task_thread is not None
        self.choose_music_button.setDisabled(busy)
        self.analyse_button.setEnabled(self._song is not None and not busy)
        self.footage_button.setEnabled(self._analysis is not None and not busy)
        self.strategy_combo.setEnabled(self._analysis is not None and not busy)
        self.generate_button.setEnabled(False)
        self.cancel_button.setEnabled(busy)

    def load_demo_state(self) -> None:
        duration = 174.0
        peaks = tuple(
            min(1.0, 0.18 + 0.58 * abs(math.sin(index * 0.17)) + (index % 13) * 0.018)
            for index in range(720)
        )
        song = SongMetadata(
            path=Path("Glass Transit.wav"),
            duration_seconds=duration,
            sample_rate=48000,
            channels=2,
            codec="pcm_s24le",
            waveform_peaks=peaks,
        )
        events: list[MusicalEvent] = []
        for index, timestamp in enumerate(float(value) for value in range(2, 173, 2)):
            events.append(MusicalEvent(EventKind.KICK, timestamp, 0.68 + (index % 4) * 0.08))
            if index % 2:
                events.append(MusicalEvent(EventKind.SNARE, timestamp + 0.52, 0.78))
            events.append(MusicalEvent(EventKind.HI_HAT, timestamp + 0.26, 0.55))
            if index % 3 == 0:
                events.append(MusicalEvent(EventKind.BASS, timestamp + 0.1, 0.74))
            if index % 8 == 0:
                events.append(MusicalEvent(EventKind.VOCAL, timestamp + 0.7, 0.62))
        analysis = MusicAnalysis(
            song=song,
            stems=tuple(
                StemArtifact(name, Path(f"{name}.wav")) for name in ("drums", "bass", "vocals")
            ),
            events=tuple(events),
            model_name="htdemucs_6s",
        )
        self._song = song
        self._analysis = analysis
        self.song_name.setText(song.path.name)
        self.song_meta.setText("2:54 · 48.0 kHz · 2 ch · PCM_S24LE")
        self.preview_eyebrow.setText("STRUCTURE READY")
        self.preview_title.setText("Now bring in\nthe footage.")
        self.timeline.set_analysis(analysis)
        self.timeline_meta.setText(f"{len(events)} EVENTS · HTDEMUCS_6S")
        self.preview_body.setText(
            f"{len(events)} musical events are ready. "
            "Import clips to generate a complete first cut."
        )
        self.task_title.setText("STRUCTURE READY")
        self.task_detail.setText("Import footage to generate the first cut")
        self.task_progress.setValue(100)
        self._sync_state()
