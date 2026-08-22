from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QStandardPaths,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
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

from kinebeat.domain import (
    DEFAULT_EFFECT_MAPPINGS,
    EffectAction,
    EventKind,
    InstrumentMapping,
    MusicalEvent,
    MusicAnalysis,
    ProjectFormatError,
    ProjectState,
    SongMetadata,
    StemArtifact,
    load_project,
    save_project,
)
from kinebeat.processing import MusicAnalysisService, probe_song
from kinebeat.ui.tasks import TaskWorker
from kinebeat.ui.timeline import MusicTimeline

AUDIO_FILTER = "Music files (*.wav *.mp3 *.flac *.m4a *.aac *.ogg *.opus);;All files (*.*)"
VIDEO_FILTER = "Video files (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.mts *.m2ts);;All files (*.*)"
PROJECT_FILTER = "Kinebeat projects (*.kinebeat);;All files (*.*)"
INSTRUMENT_LABELS = {
    EventKind.KICK: "KICK",
    EventKind.SNARE: "SNARE",
    EventKind.HI_HAT: "HI-HAT",
    EventKind.BASS: "BASS",
    EventKind.VOCAL: "VOCAL",
}
EFFECT_OPTIONS = (
    (EffectAction.CUT, "Cut"),
    (EffectAction.RANDOM_EFFECT, "Random effect"),
    (EffectAction.ADD_INTENSITY, "Add more intensity"),
    (EffectAction.ADD_AMBIANCE, "Add more ambiance"),
    (EffectAction.LIGHT_EFFECT, "Light effect · 0.2 s"),
    (EffectAction.TIME_BEND, "Time bend"),
    (EffectAction.NO_ACTION, "No action"),
)


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
    def __init__(self, *, animations_enabled: bool | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Kinebeat")
        self.resize(1480, 900)
        self.setMinimumSize(1120, 720)
        self._song: SongMetadata | None = None
        self._analysis: MusicAnalysis | None = None
        self._video_paths: tuple[Path, ...] = ()
        self._project_path: Path | None = None
        self._dirty = False
        self._loading_project = False
        self._pending_playhead_seconds = 0.0
        self._animations_enabled = (
            QApplication.isEffectEnabled(Qt.UIEffect.UI_AnimateCombo)
            if animations_enabled is None
            else animations_enabled
        )
        self._save_feedback_animation: QPropertyAnimation | None = None
        self._task_thread: QThread | None = None
        self._task_worker: TaskWorker | None = None
        self._build_ui()
        self._setup_save_feedback()
        self._setup_playback()
        self._setup_shortcuts()
        self._update_window_title()
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
        layout.addWidget(wordmark)
        layout.addWidget(strapline)
        layout.addStretch()
        self.open_project_button = QPushButton("Open project")
        self.open_project_button.setObjectName("quietButton")
        self.open_project_button.clicked.connect(self._open_project)
        self.save_project_button = QPushButton("Save project")
        self.save_project_button.setObjectName("quietButton")
        self.save_project_button.setProperty("saveState", "idle")
        self.save_project_button.setFixedWidth(112)
        self.save_project_button.clicked.connect(self._save_project)
        layout.addWidget(self.open_project_button)
        layout.addWidget(self.save_project_button)
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
        self.footage_copy = QLabel("Import clips after the musical structure is ready.")
        self.footage_copy.setObjectName("bodyMuted")
        self.footage_copy.setWordWrap(True)
        self.footage_button = QPushButton("Import video clips")
        self.footage_button.setObjectName("secondaryButton")
        self.footage_button.clicked.connect(self._choose_video_clips)
        footage_layout.addWidget(self.footage_copy)
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
        self.play_button = QPushButton("PLAY")
        self.play_button.setObjectName("transportButton")
        self.play_button.setFixedWidth(70)
        self.play_button.clicked.connect(self._toggle_playback)
        self.timecode_label = QLabel("0:00 / 0:00")
        self.timecode_label.setObjectName("timelineMeta")
        self.timecode_label.setMinimumWidth(92)
        self.timeline_meta = QLabel("WAITING FOR MUSIC")
        self.timeline_meta.setObjectName("timelineMeta")
        timeline_header_layout.addWidget(timeline_title)
        timeline_header_layout.addSpacing(10)
        timeline_header_layout.addWidget(self.play_button)
        timeline_header_layout.addWidget(self.timecode_label)
        timeline_header_layout.addStretch()
        timeline_header_layout.addWidget(self.timeline_meta)
        self.timeline = MusicTimeline()
        self.timeline.seekRequested.connect(self._seek_timeline)
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
        self.strategy_combo.currentTextChanged.connect(self._strategy_changed)
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(helper)
        layout.addSpacing(12)
        layout.addWidget(strategy_label)
        layout.addWidget(self.strategy_combo)
        layout.addSpacing(12)
        self.mapping_combos: dict[EventKind, QComboBox] = {}
        for mapping in DEFAULT_EFFECT_MAPPINGS:
            layout.addWidget(self._mapping_row(mapping.instrument, mapping.action))
        layout.addStretch()
        self.generate_button = QPushButton("Generate first cut")
        self.generate_button.setObjectName("primaryButton")
        layout.addWidget(self.generate_button)
        return inspector

    def _mapping_row(self, instrument: EventKind, default_action: EffectAction) -> QFrame:
        row = QFrame()
        row.setObjectName("mappingRow")
        row.setMinimumHeight(68)
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 7, 0, 8)
        layout.setSpacing(5)
        instrument_label = QLabel(INSTRUMENT_LABELS[instrument])
        instrument_label.setObjectName("mappingInstrument")
        effect_combo = QComboBox()
        effect_combo.setObjectName("mappingCombo")
        for action, label in EFFECT_OPTIONS:
            effect_combo.addItem(label, action.value)
        effect_combo.setCurrentIndex(effect_combo.findData(default_action.value))
        effect_combo.currentIndexChanged.connect(self._mapping_changed)
        self.mapping_combos[instrument] = effect_combo
        layout.addWidget(instrument_label)
        layout.addWidget(effect_combo)
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

    def _setup_playback(self) -> None:
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.8)
        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.positionChanged.connect(self._playback_position_changed)
        self.media_player.playbackStateChanged.connect(self._playback_state_changed)
        self.media_player.mediaStatusChanged.connect(self._media_status_changed)

    def _setup_save_feedback(self) -> None:
        self._save_feedback_effect = QGraphicsOpacityEffect(self.save_project_button)
        self._save_feedback_effect.setOpacity(1.0)
        self.save_project_button.setGraphicsEffect(self._save_feedback_effect)
        self._save_feedback_timer = QTimer(self)
        self._save_feedback_timer.setSingleShot(True)
        self._save_feedback_timer.timeout.connect(self._begin_save_feedback_reset)

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self._open_project)
        QShortcut(QKeySequence.StandardKey.Save, self, activated=self._save_project)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._toggle_playback)

    @Slot()
    def _open_project(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open Kinebeat project", "", PROJECT_FILTER)
        if not path:
            return
        try:
            state = load_project(Path(path))
        except ProjectFormatError as error:
            QMessageBox.warning(self, "Kinebeat could not open the project", str(error))
            return
        self._apply_project(Path(path), state)

    @Slot()
    def _save_project(self) -> None:
        path = self._project_path
        if path is None:
            selected, _ = QFileDialog.getSaveFileName(
                self, "Save Kinebeat project", "Untitled.kinebeat", PROJECT_FILTER
            )
            if not selected:
                return
            path = Path(selected)
            if path.suffix.lower() != ".kinebeat":
                path = path.with_suffix(".kinebeat")
        try:
            save_project(path, self._project_state())
        except OSError as error:
            QMessageBox.warning(self, "Kinebeat could not save the project", str(error))
            return
        self._project_path = path.resolve()
        self._set_dirty(False)
        self._show_save_feedback()
        self.task_title.setText("PROJECT SAVED")
        self.task_detail.setText(str(self._project_path))

    def _show_save_feedback(self) -> None:
        self._save_feedback_timer.stop()
        self._stop_save_feedback_animation()
        self._set_save_button_state("Saved", "saved")
        if self._animations_enabled:
            self._save_feedback_effect.setOpacity(0.45)
            self._animate_save_opacity(0.45, 1.0, 220)
        else:
            self._save_feedback_effect.setOpacity(1.0)
        self._save_feedback_timer.start(1400)

    @Slot()
    def _begin_save_feedback_reset(self) -> None:
        self._stop_save_feedback_animation()
        if not self._animations_enabled:
            self._restore_save_button()
            return
        self._animate_save_opacity(
            self._save_feedback_effect.opacity(),
            0.55,
            90,
            self._restore_save_button_animated,
        )

    def _restore_save_button_animated(self) -> None:
        self._set_save_button_state("Save project", "idle")
        self._animate_save_opacity(0.55, 1.0, 150)

    def _restore_save_button(self) -> None:
        self._stop_save_feedback_animation()
        self._set_save_button_state("Save project", "idle")
        self._save_feedback_effect.setOpacity(1.0)

    def _set_save_button_state(self, text: str, state: str) -> None:
        self.save_project_button.setText(text)
        self.save_project_button.setAccessibleName(text)
        self.save_project_button.setProperty("saveState", state)
        self.save_project_button.style().unpolish(self.save_project_button)
        self.save_project_button.style().polish(self.save_project_button)

    def _animate_save_opacity(
        self,
        start: float,
        end: float,
        duration_ms: int,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        animation = QPropertyAnimation(self._save_feedback_effect, b"opacity", self)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setDuration(duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.OutQuart)
        if on_finished:
            animation.finished.connect(on_finished)
        animation.finished.connect(lambda: self._forget_save_feedback_animation(animation))
        self._save_feedback_animation = animation
        animation.start()

    def _forget_save_feedback_animation(self, animation: QPropertyAnimation) -> None:
        if self._save_feedback_animation is animation:
            self._save_feedback_animation = None
        animation.deleteLater()

    def _stop_save_feedback_animation(self) -> None:
        if self._save_feedback_animation is not None:
            self._save_feedback_animation.stop()
            self._save_feedback_animation.deleteLater()
            self._save_feedback_animation = None

    def _project_state(self) -> ProjectState:
        return ProjectState(
            song=self._song,
            analysis=self._analysis,
            video_paths=self._video_paths,
            footage_strategy=self.strategy_combo.currentText(),
            playhead_seconds=self.timeline.position_seconds,
            effect_mappings=tuple(
                InstrumentMapping(instrument, EffectAction(combo.currentData()))
                for instrument, combo in self.mapping_combos.items()
            ),
        )

    def _apply_project(self, path: Path, state: ProjectState) -> None:
        self.media_player.stop()
        self._loading_project = True
        self._song = state.song
        self._analysis = state.analysis
        self._video_paths = state.video_paths
        self._project_path = path.resolve()
        strategy_index = self.strategy_combo.findText(state.footage_strategy)
        self.strategy_combo.setCurrentIndex(max(0, strategy_index))
        for default in DEFAULT_EFFECT_MAPPINGS:
            combo = self.mapping_combos[default.instrument]
            combo.setCurrentIndex(combo.findData(default.action.value))
        for mapping in state.effect_mappings:
            combo = self.mapping_combos.get(mapping.instrument)
            if combo is not None:
                action_index = combo.findData(mapping.action.value)
                if action_index >= 0:
                    combo.setCurrentIndex(action_index)
        self._loading_project = False

        if self._song:
            self.song_name.setText(self._song.path.name)
            self.song_meta.setText(
                f"{self._song.display_duration} · {self._song.sample_rate / 1000:.1f} kHz · "
                f"{self._song.channels} ch · {self._song.codec.upper()}"
            )
            if self._analysis:
                self.timeline.set_analysis(self._analysis)
                self.timeline_meta.setText(
                    f"{len(self._analysis.events)} EVENTS · {self._analysis.model_name.upper()}"
                )
                self.preview_eyebrow.setText("PROJECT LOADED")
                self.preview_title.setText("Your cut is ready\nto keep shaping.")
                self.preview_body.setText(
                    f"{len(self._analysis.events)} musical events and "
                    f"{len(self._video_paths)} video clips were restored."
                )
            else:
                self.timeline.set_song(self._song)
                self.timeline_meta.setText(f"{self._song.display_duration} · READY TO ANALYSE")
                self.preview_eyebrow.setText("PROJECT LOADED")
                self.preview_title.setText("Ready to find\nthe structure.")
                self.preview_body.setText(
                    "Analyse the song to separate instruments and rebuild its musical events."
                )
        else:
            self.song_name.setText("No song loaded")
            self.song_meta.setText("Your music stays on this computer.")
            self.timeline.set_song(None)
            self.timeline_meta.setText("WAITING FOR MUSIC")
            self.preview_eyebrow.setText("START WITH THE SOUND")
            self.preview_title.setText("Your song sets\nthe timeline.")
            self.preview_body.setText(
                "Kinebeat separates the instruments, finds their events, "
                "and builds an edit you can keep refining."
            )

        self._update_footage_copy()
        self._pending_playhead_seconds = state.playhead_seconds
        self.timeline.set_position(state.playhead_seconds)
        self._update_timecode(state.playhead_seconds)
        self._set_song_playback_source(state.playhead_seconds)
        self._set_dirty(False)
        self._sync_state()

        missing = [media_path for media_path in self._all_media_paths() if not media_path.is_file()]
        if missing:
            preview = "\n".join(str(media_path) for media_path in missing[:5])
            extra = f"\n…and {len(missing) - 5} more" if len(missing) > 5 else ""
            QMessageBox.warning(
                self,
                "Some project media is missing",
                f"The project opened, but these files could not be found:\n\n{preview}{extra}",
            )

    def _all_media_paths(self) -> tuple[Path, ...]:
        song_paths = (self._song.path,) if self._song else ()
        return song_paths + self._video_paths

    @Slot()
    def _choose_video_clips(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import video clips", "", VIDEO_FILTER)
        if not paths:
            return
        existing = {path.resolve() for path in self._video_paths}
        imported = list(self._video_paths)
        for value in paths:
            path = Path(value).resolve()
            if path not in existing:
                existing.add(path)
                imported.append(path)
        self._video_paths = tuple(imported)
        self._update_footage_copy()
        self.preview_eyebrow.setText("FOOTAGE READY")
        self.preview_title.setText("Ready to build\nthe first cut.")
        self.preview_body.setText(
            f"{len(self._video_paths)} clips will be selected using "
            f"{self.strategy_combo.currentText().lower()}."
        )
        self.task_title.setText("FOOTAGE READY")
        self.task_detail.setText(f"{len(self._video_paths)} video clips imported")
        self._set_dirty(True)
        self._sync_state()

    def _update_footage_copy(self) -> None:
        count = len(self._video_paths)
        if not count:
            self.footage_copy.setText("Import clips after the musical structure is ready.")
            self.footage_button.setText("Import video clips")
            return
        noun = "clip" if count == 1 else "clips"
        names = ", ".join(path.name for path in self._video_paths[:3])
        if count > 3:
            names += f" +{count - 3} more"
        self.footage_copy.setText(f"{count} {noun} imported\n{names}")
        self.footage_button.setText("Add video clips")

    @Slot(str)
    def _strategy_changed(self, _strategy: str) -> None:
        if not self._loading_project and self._analysis:
            self._set_dirty(True)

    @Slot()
    def _mapping_changed(self) -> None:
        if not self._loading_project and self._analysis:
            self._set_dirty(True)

    @Slot()
    def _toggle_playback(self) -> None:
        if not self._song or not self._song.path.is_file():
            QMessageBox.information(
                self, "Music is unavailable", "Load or reconnect the project music before playback."
            )
            return
        if self.media_player.playbackState() is QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            if self.timeline.position_seconds >= self._song.duration_seconds - 0.05:
                self._seek_timeline(0.0)
            self.media_player.play()

    @Slot(float)
    def _seek_timeline(self, seconds: float) -> None:
        self._pending_playhead_seconds = max(0.0, seconds)
        self.timeline.set_position(seconds)
        self._update_timecode(seconds)
        if self._song and self._song.path.is_file():
            self.media_player.setPosition(round(seconds * 1000))

    @Slot(int)
    def _playback_position_changed(self, milliseconds: int) -> None:
        seconds = milliseconds / 1000.0
        self.timeline.set_position(seconds)
        self._update_timecode(seconds)

    @Slot(QMediaPlayer.PlaybackState)
    def _playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "PAUSE" if state is QMediaPlayer.PlaybackState.PlayingState else "PLAY"
        )

    @Slot(QMediaPlayer.MediaStatus)
    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.media_player.setPosition(round(self._pending_playhead_seconds * 1000))

    def _set_song_playback_source(self, position_seconds: float = 0.0) -> None:
        self.media_player.stop()
        self._pending_playhead_seconds = position_seconds
        if self._song and self._song.path.is_file():
            self.media_player.setSource(QUrl.fromLocalFile(str(self._song.path.resolve())))
        else:
            self.media_player.setSource(QUrl())

    def _update_timecode(self, seconds: float) -> None:
        duration = self._song.duration_seconds if self._song else 0.0
        self.timecode_label.setText(f"{self._format_time(seconds)} / {self._format_time(duration)}")

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes, whole_seconds = divmod(max(0, round(seconds)), 60)
        return f"{minutes}:{whole_seconds:02d}"

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.setWindowModified(dirty)
        self._update_window_title()

    def _update_window_title(self) -> None:
        name = self._project_path.stem if self._project_path else "Untitled"
        self.setWindowTitle(f"{name}[*] — Kinebeat")

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
        self.timeline.set_position(0.0)
        self.timeline_meta.setText(f"{result.display_duration} · READY TO ANALYSE")
        self._update_timecode(0.0)
        self._set_song_playback_source()
        self._set_dirty(True)

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
        self._set_dirty(True)

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
        for combo in self.mapping_combos.values():
            combo.setEnabled(self._analysis is not None and not busy)
        self.generate_button.setEnabled(
            self._analysis is not None and bool(self._video_paths) and not busy
        )
        self.play_button.setEnabled(
            self._song is not None and self._song.path.is_file() and not busy
        )
        self.open_project_button.setEnabled(not busy)
        self.save_project_button.setEnabled(
            (self._song is not None or bool(self._video_paths)) and not busy
        )
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
        self._video_paths = ()
        self.song_name.setText(song.path.name)
        self.song_meta.setText("2:54 · 48.0 kHz · 2 ch · PCM_S24LE")
        self.preview_eyebrow.setText("STRUCTURE READY")
        self.preview_title.setText("Now bring in\nthe footage.")
        self.timeline.set_analysis(analysis)
        self.timeline.set_position(0.0)
        self.timeline_meta.setText(f"{len(events)} EVENTS · HTDEMUCS_6S")
        self._update_timecode(0.0)
        self._set_song_playback_source()
        self.preview_body.setText(
            f"{len(events)} musical events are ready. "
            "Import clips to generate a complete first cut."
        )
        self.task_title.setText("STRUCTURE READY")
        self.task_detail.setText("Import footage to generate the first cut")
        self.task_progress.setValue(100)
        self._set_dirty(False)
        self._sync_state()
