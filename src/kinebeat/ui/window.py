from __future__ import annotations

import math
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRect,
    QRunnable,
    QStandardPaths,
    Qt,
    QThread,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoFrame, QVideoSink
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
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from kinebeat.domain import (
    DEFAULT_EFFECT_MAPPINGS,
    EffectAction,
    EventKind,
    GeneratedTimeline,
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
from kinebeat.processing import (
    MusicAnalysisService,
    VideoEditPreview,
    generate_video_edit_preview,
    inspect_video_media,
    probe_song,
)
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
    (EffectAction.GLITCH, "Glitch"),
    (EffectAction.VHS, "VHS"),
    (EffectAction.SILHOUETTE_STRETCH, "Silhouette edge stretch"),
    (EffectAction.VIDEO_VOLUME, "Video volume · XYT"),
    (EffectAction.DATAMOSH, "Datamosh"),
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


class VideoPreviewCanvas(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("videoPreview")
        self._image: QImage | None = None
        self.video_sink = QVideoSink(self)
        self.video_sink.videoFrameChanged.connect(self._frame_changed)

    def clear(self) -> None:
        self._image = None
        self.update()

    @Slot(QVideoFrame)
    def _frame_changed(self, frame: QVideoFrame) -> None:
        if not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._image = image.copy()
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        if self._image is None:
            return
        target_size = self._image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(
            (self.width() - target_size.width()) // 2,
            (self.height() - target_size.height()) // 2,
            target_size.width(),
            target_size.height(),
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self._image)


class MediaLibraryRow(QFrame):
    removeRequested = Signal(Path)

    def __init__(self, path: Path, index: int) -> None:
        super().__init__()
        self.path = path
        self.setObjectName("mediaLibraryRow")
        self.setProperty("health", "checking")
        self.setToolTip(str(path))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 8, 7, 8)
        layout.setSpacing(8)

        self.thumbnail = QLabel("LOADING")
        self.thumbnail.setObjectName("mediaThumbnail")
        self.thumbnail.setProperty("state", "loading")
        self.thumbnail.setFixedSize(72, 45)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        details = QVBoxLayout()
        details.setSpacing(1)
        name = QLabel(_compact_media_name(path.name, 18))
        name.setObjectName("mediaName")
        name.setToolTip(path.name)
        self._media_kind = path.suffix.removeprefix(".").upper() or "FILE"
        self._media_index = index
        self.meta = QLabel()
        self.meta.setObjectName("mediaMeta")
        self._set_meta_status("CHECKING")
        details.addWidget(name)
        details.addWidget(self.meta)

        self.remove_button = QPushButton("REMOVE")
        self.remove_button.setObjectName("mediaRemoveButton")
        self.remove_button.setAccessibleName(f"Remove {path.name}")
        self.remove_button.setToolTip(f"Remove {path.name} from this project")
        self.remove_button.setFixedWidth(58)
        self.remove_button.clicked.connect(
            lambda _checked=False: self.removeRequested.emit(self.path)
        )

        layout.addWidget(self.thumbnail)
        layout.addLayout(details, 1)
        layout.addWidget(self.remove_button)

    def set_thumbnail(self, image: QImage) -> None:
        self.thumbnail.setText("")
        self.thumbnail.setPixmap(QPixmap.fromImage(image))
        self._set_media_state("ready")
        self._set_meta_status("READY")
        self.setToolTip(str(self.path))

    def set_broken(self, reason: str) -> None:
        self.thumbnail.setPixmap(QPixmap())
        self.thumbnail.setText("BROKEN")
        self._set_media_state("broken")
        self._set_meta_status("BROKEN")
        self.setToolTip(f"{self.path}\n\nBroken: {reason}")

    def _set_meta_status(self, status: str) -> None:
        self.meta.setText(f"{self._media_index:02d} · {self._media_kind} · {status}")

    def _set_media_state(self, state: str) -> None:
        self.setProperty("health", state)
        self.thumbnail.setProperty("state", state)
        for widget in (self, self.thumbnail, self.meta):
            widget.style().unpolish(widget)
            widget.style().polish(widget)


class MediaThumbnailSignals(QObject):
    ready = Signal(Path, object, float)
    failed = Signal(Path, str)


class MediaThumbnailTask(QRunnable):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.signals = MediaThumbnailSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = inspect_video_media(self.path)
            pixels = result.thumbnail
            image = QImage(
                pixels.data,
                pixels.shape[1],
                pixels.shape[0],
                pixels.strides[0],
                QImage.Format.Format_RGB888,
            ).copy()
        except (OSError, ValueError) as error:
            self.signals.failed.emit(self.path, str(error))
        else:
            self.signals.ready.emit(self.path, image, result.duration_seconds)


def _compact_media_name(name: str, limit: int = 24) -> str:
    if len(name) <= limit:
        return name
    suffix = Path(name).suffix
    stem_limit = max(6, limit - len(suffix) - 1)
    return f"{Path(name).stem[:stem_limit]}…{suffix}"


class KinebeatWindow(QMainWindow):
    def __init__(self, *, animations_enabled: bool | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Kinebeat")
        self.resize(1480, 900)
        self.setMinimumSize(1120, 720)
        self._song: SongMetadata | None = None
        self._analysis: MusicAnalysis | None = None
        self._generated_timeline: GeneratedTimeline | None = None
        self._preview_path: Path | None = None
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
        self._task_failed_message: str | None = None
        self._thumbnail_pool = QThreadPool(self)
        self._thumbnail_pool.setMaxThreadCount(4)
        self._thumbnail_cache: dict[tuple[Path, int, int], QImage] = {}
        self._media_durations: dict[tuple[Path, int, int], float] = {}
        self._thumbnail_failures: dict[tuple[Path, int, int], str] = {}
        self._thumbnail_tasks: dict[Path, MediaThumbnailTask] = {}
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
        footage_layout.addLayout(self._step_heading("02", "Media library"))
        self.footage_copy = QLabel("No video clips yet.")
        self.footage_copy.setObjectName("bodyMuted")
        self.footage_copy.setWordWrap(True)
        self.footage_button = QPushButton("Import video clips")
        self.footage_button.setObjectName("secondaryButton")
        self.footage_button.clicked.connect(self._choose_video_clips)
        self.media_library_scroll = QScrollArea()
        self.media_library_scroll.setObjectName("mediaLibraryScroll")
        self.media_library_scroll.setWidgetResizable(True)
        self.media_library_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.media_library_content = QWidget()
        self.media_library_content.setObjectName("mediaLibraryContent")
        self.media_library_layout = QVBoxLayout(self.media_library_content)
        self.media_library_layout.setContentsMargins(0, 0, 0, 0)
        self.media_library_layout.setSpacing(5)
        self.media_library_scroll.setWidget(self.media_library_content)
        self._media_rows: list[MediaLibraryRow] = []
        footage_layout.addWidget(self.footage_copy)
        footage_layout.addWidget(self.footage_button)
        footage_layout.addWidget(self.media_library_scroll, 1)
        layout.addWidget(music_section)
        layout.addWidget(footage_section, 1)
        self._refresh_media_library()
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
        preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_stack = QStackedWidget()
        self.preview_stack.setObjectName("previewStack")
        preview_message = QWidget()
        message_layout = QVBoxLayout(preview_message)
        message_layout.setContentsMargins(40, 30, 40, 30)
        message_layout.addStretch()
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
        message_layout.addWidget(self.preview_eyebrow)
        message_layout.addWidget(self.preview_title)
        message_layout.addSpacing(6)
        message_layout.addWidget(self.preview_body)
        message_layout.addStretch()
        self.video_widget = VideoPreviewCanvas()
        self.preview_stack.addWidget(preview_message)
        self.preview_stack.addWidget(self.video_widget)
        preview_layout.addWidget(self.preview_stack)
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
        title = QLabel("Video edit rules")
        title.setObjectName("sectionTitle")
        helper = QLabel("Each detected instrument can cut or trigger a rendered effect.")
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
        self.generate_button = QPushButton("Generate video edit")
        self.generate_button.setObjectName("primaryButton")
        self.generate_button.clicked.connect(self._generate_video_edit)
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
        self.video_player = QMediaPlayer(self)
        self.video_player.setVideoSink(self.video_widget.video_sink)
        self.video_player.mediaStatusChanged.connect(self._video_media_status_changed)
        self.video_player.errorOccurred.connect(self._video_playback_failed)
        self._video_sync_timer = QTimer(self)
        self._video_sync_timer.setSingleShot(True)
        self._video_sync_timer.setInterval(1500)
        self._video_sync_timer.timeout.connect(self._sync_video_once)

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
            generated_timeline=self._generated_timeline,
        )

    def _apply_project(self, path: Path, state: ProjectState) -> None:
        self.media_player.stop()
        self._set_video_preview_source(None)
        self._loading_project = True
        self._song = state.song
        self._analysis = state.analysis
        self._generated_timeline = state.generated_timeline
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
                self.timeline.set_first_cut(self._generated_timeline)
                if self._generated_timeline:
                    self.timeline_meta.setText(
                        f"{len(self._generated_timeline.clips)} EDITS · "
                        f"{len(self._analysis.events)} EVENTS"
                    )
                    self.preview_eyebrow.setText("EDIT DECISIONS RESTORED")
                    self.preview_title.setText("Build the playable\nvideo preview.")
                    self.preview_body.setText(
                        f"{len(self._generated_timeline.clips)} beat-synced edits and "
                        f"{len(self._video_paths)} source clips were restored. Generate the "
                        "video edit to render its lightweight preview."
                    )
                else:
                    self.timeline_meta.setText(
                        f"{len(self._analysis.events)} EVENTS · {self._analysis.model_name.upper()}"
                    )
                    self.preview_eyebrow.setText("PROJECT LOADED")
                    self.preview_title.setText("Ready to build\nthe video edit.")
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

        missing_song = self._song and not self._song.path.is_file()
        if missing_song:
            QMessageBox.warning(
                self,
                "Project music is missing",
                f"The project opened, but its music could not be found:\n\n{self._song.path}",
            )

    @Slot()
    def _choose_video_clips(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Import video clips", "", VIDEO_FILTER)
        if not paths:
            return
        existing = {path.resolve() for path in self._video_paths}
        imported = list(self._video_paths)
        added_count = 0
        for value in paths:
            path = Path(value).resolve()
            if path not in existing:
                existing.add(path)
                imported.append(path)
                added_count += 1
        if not added_count:
            return
        self._video_paths = tuple(imported)
        self._update_footage_copy()
        if self._generated_timeline:
            self.task_title.setText("CHECKING MEDIA")
            self.task_detail.setText(
                f"Checking {added_count} added video {'clip' if added_count == 1 else 'clips'}"
            )
        else:
            self.preview_stack.setCurrentIndex(0)
            self.preview_eyebrow.setText("CHECKING FOOTAGE")
            self.preview_title.setText("Verifying your\nvideo clips.")
            self.preview_body.setText(
                "Kinebeat is checking that each file has decodable video and usable timing. "
                "Broken clips stay visible in the Media library and will be skipped."
            )
            self.task_title.setText("CHECKING MEDIA")
            self.task_detail.setText(
                f"Checking {added_count} video {'clip' if added_count == 1 else 'clips'}"
            )
        self._set_dirty(True)
        self._sync_state()

    def _update_footage_copy(self) -> None:
        self._refresh_media_library()
        self._update_footage_summary()

    def _update_footage_summary(self) -> None:
        count = len(self._video_paths)
        if not count:
            self.footage_copy.setText("No video clips yet.")
            self.footage_button.setText("Import video clips")
            return

        ready_count = len(self._verified_video_paths())
        broken_count = len(self._broken_video_paths())
        checking_count = max(0, count - ready_count - broken_count)
        states = []
        if ready_count:
            states.append(f"{ready_count} ready")
        if checking_count:
            states.append(f"{checking_count} checking")
        if broken_count:
            states.append(f"{broken_count} broken")
        self.footage_copy.setText(" · ".join(states))
        self.footage_button.setText("Add video clips")

    def _refresh_media_library(self) -> None:
        while self.media_library_layout.count():
            item = self.media_library_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()
        self._media_rows = []

        if not self._video_paths:
            empty = QLabel("Import footage to fill your first cut.")
            empty.setObjectName("mediaEmptyState")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.media_library_layout.addWidget(empty)
            self.media_library_layout.addStretch()
            return

        for index, path in enumerate(self._video_paths, start=1):
            row = MediaLibraryRow(path, index)
            row.removeRequested.connect(self._remove_video_clip)
            self._media_rows.append(row)
            self.media_library_layout.addWidget(row)
            self._load_media_thumbnail(row)
        self.media_library_layout.addStretch()

    def _load_media_thumbnail(self, row: MediaLibraryRow) -> None:
        key = self._thumbnail_key(row.path)
        image = self._thumbnail_cache.get(key)
        if image is not None:
            row.set_thumbnail(image)
            return
        if reason := self._thumbnail_failures.get(key):
            row.set_broken(reason)
            return
        if not row.path.is_file():
            reason = "The file is missing or no longer accessible."
            self._thumbnail_failures[key] = reason
            row.set_broken(reason)
            return

        source = row.path.resolve()
        if source in self._thumbnail_tasks:
            return
        task = MediaThumbnailTask(source)
        task.signals.ready.connect(self._media_thumbnail_ready)
        task.signals.failed.connect(self._media_thumbnail_failed)
        self._thumbnail_tasks[source] = task
        self._thumbnail_pool.start(task)

    @Slot(Path, object, float)
    def _media_thumbnail_ready(
        self, path: Path, value: object, duration_seconds: float = 1.0
    ) -> None:
        self._thumbnail_tasks.pop(path.resolve(), None)
        if not isinstance(value, QImage):
            self._media_thumbnail_failed(path, "The decoder returned an invalid preview frame.")
            return
        key = self._thumbnail_key(path)
        self._thumbnail_failures.pop(key, None)
        self._thumbnail_cache[key] = value
        self._media_durations[key] = duration_seconds
        for row in self._media_rows:
            if row.path.resolve() == path.resolve():
                row.set_thumbnail(value)
        self._media_check_state_changed()

    @Slot(Path, str)
    def _media_thumbnail_failed(self, path: Path, reason: str) -> None:
        self._thumbnail_tasks.pop(path.resolve(), None)
        self._thumbnail_failures[self._thumbnail_key(path)] = reason
        for row in self._media_rows:
            if row.path.resolve() == path.resolve():
                row.set_broken(reason)
        self._media_check_state_changed()

    def _media_check_state_changed(self) -> None:
        self._update_footage_summary()
        ready_count = len(self._verified_video_paths())
        broken_count = len(self._broken_video_paths())
        checking_count = len(self._video_paths) - ready_count - broken_count
        if checking_count > 0:
            self.task_title.setText("CHECKING MEDIA")
            self.task_detail.setText(
                f"Checking {checking_count} video {'clip' if checking_count == 1 else 'clips'}"
            )
        elif broken_count and ready_count:
            self.task_title.setText("MEDIA CHECK COMPLETE")
            self.task_detail.setText(
                f"{ready_count} ready · {broken_count} broken and excluded from generation"
            )
        elif broken_count:
            self.task_title.setText("NO USABLE FOOTAGE")
            self.task_detail.setText(
                f"{broken_count} broken {'clip' if broken_count == 1 else 'clips'} · "
                "remove or replace them"
            )
        elif ready_count:
            self.task_title.setText("FOOTAGE READY")
            self.task_detail.setText(
                f"{ready_count} video {'clip' if ready_count == 1 else 'clips'} checked"
            )
        if checking_count <= 0 and not self._generated_timeline:
            self.preview_stack.setCurrentIndex(0)
            if ready_count:
                self.preview_eyebrow.setText("FOOTAGE READY")
                self.preview_title.setText("Ready to build\nthe video edit.")
                skipped = (
                    f" {broken_count} broken {'clip was' if broken_count == 1 else 'clips were'} "
                    "excluded."
                    if broken_count
                    else ""
                )
                self.preview_body.setText(
                    f"{ready_count} checked {'clip is' if ready_count == 1 else 'clips are'} ready "
                    f"for {self.strategy_combo.currentText().lower()}.{skipped}"
                )
            elif broken_count:
                self.preview_eyebrow.setText("NO USABLE FOOTAGE")
                self.preview_title.setText("Replace the broken\nvideo clips.")
                self.preview_body.setText(
                    "The files remain in the Media library so you can identify and remove them."
                )
        self._sync_state()

    def _verified_video_paths(self) -> tuple[Path, ...]:
        return tuple(
            path for path in self._video_paths if self._thumbnail_key(path) in self._thumbnail_cache
        )

    def _broken_video_paths(self) -> tuple[Path, ...]:
        return tuple(
            path
            for path in self._video_paths
            if self._thumbnail_key(path) in self._thumbnail_failures
        )

    def _verified_source_durations(self, paths: tuple[Path, ...]) -> dict[Path, float]:
        return {path: self._media_durations[self._thumbnail_key(path)] for path in paths}

    @staticmethod
    def _thumbnail_key(path: Path) -> tuple[Path, int, int]:
        source = path.resolve()
        try:
            status = source.stat()
        except OSError:
            return source, 0, 0
        return source, status.st_mtime_ns, status.st_size

    @Slot(Path)
    def _remove_video_clip(self, path: Path) -> None:
        target = path.resolve()
        remaining = tuple(video for video in self._video_paths if video.resolve() != target)
        if len(remaining) == len(self._video_paths):
            return

        removed_from_edit = bool(
            self._generated_timeline
            and any(clip.source_path.resolve() == target for clip in self._generated_timeline.clips)
        )
        self._video_paths = remaining
        if removed_from_edit:
            self.media_player.pause()
            self.video_player.pause()
            self._generated_timeline = None
            self.timeline.set_first_cut(None)
            self._set_video_preview_source(None)
            if remaining:
                self.preview_eyebrow.setText("MEDIA LIBRARY CHANGED")
                self.preview_title.setText("Ready to rebuild\nthe video edit.")
                self.preview_body.setText(
                    f"{path.name} was removed from the current edit. Generate again to create "
                    "a preview using the remaining footage."
                )
                self.task_title.setText("VIDEO EDIT NEEDS REBUILDING")
                self.task_detail.setText(f"Removed {path.name} from the generated timeline")
            else:
                self.preview_eyebrow.setText("MEDIA LIBRARY EMPTY")
                self.preview_title.setText("Add footage to\nrebuild the edit.")
                self.preview_body.setText(
                    f"{path.name} was the final video clip. Import footage to generate a new "
                    "playable preview."
                )
                self.task_title.setText("MEDIA LIBRARY EMPTY")
                self.task_detail.setText("Import video clips to continue")
            self.task_progress.setValue(0)
        else:
            self.task_title.setText("MEDIA LIBRARY UPDATED")
            self.task_detail.setText(f"Removed {path.name}")
            if not remaining:
                self.preview_stack.setCurrentIndex(0)
                self.preview_eyebrow.setText("MEDIA LIBRARY EMPTY")
                self.preview_title.setText("Now bring in\nthe footage.")
                self.preview_body.setText("Import video clips to build the first playable edit.")

        self._update_footage_copy()
        self._set_dirty(True)
        self._sync_state()

    @Slot(str)
    def _strategy_changed(self, _strategy: str) -> None:
        if not self._loading_project and self._analysis:
            self._set_dirty(True)

    @Slot()
    def _mapping_changed(self) -> None:
        if not self._loading_project and self._analysis:
            self._set_dirty(True)
            if self._preview_path:
                self.task_title.setText("EFFECT RULES CHANGED")
                self.task_detail.setText("Regenerate the video edit to render the new effects")

    @Slot()
    def _generate_video_edit(self) -> None:
        video_paths = self._verified_video_paths()
        checking_media = bool(self._video_paths) and (
            len(video_paths) + len(self._broken_video_paths()) < len(self._video_paths)
        )
        if not self._analysis or checking_media or not video_paths:
            return
        analysis = self._analysis
        strategy = self.strategy_combo.currentText()
        effect_mappings = tuple(
            InstrumentMapping(instrument, EffectAction(combo.currentData()))
            for instrument, combo in self.mapping_combos.items()
        )
        seed = secrets.randbits(31)
        cache_location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.CacheLocation
        )
        output_path = Path(cache_location) / "previews" / f"video-edit-{seed}.mp4"
        self.generate_button.setText("Generating…")
        self.preview_stack.setCurrentIndex(0)
        self.preview_eyebrow.setText("GENERATING VIDEO EDIT")
        self.preview_title.setText("Building your\nplayable preview.")
        self.preview_body.setText(
            "Rendering a lightweight 640 × 360 proxy from your source clips. "
            "Progress stays visible below."
        )
        self._start_task(
            title="GENERATING VIDEO EDIT",
            initial_detail="Finding kick cut points",
            task=lambda **kwargs: generate_video_edit_preview(
                analysis,
                video_paths,
                strategy=strategy,
                seed=seed,
                output_path=output_path,
                effect_mappings=effect_mappings,
                source_durations=self._verified_source_durations(video_paths),
                **kwargs,
            ),
            on_success=self._video_edit_ready,
        )

    @Slot()
    def _toggle_playback(self) -> None:
        if not self._song or not self._song.path.is_file():
            QMessageBox.information(
                self, "Music is unavailable", "Load or reconnect the project music before playback."
            )
            return
        if self.media_player.playbackState() is QMediaPlayer.PlaybackState.PlayingState:
            self._video_sync_timer.stop()
            self.media_player.pause()
            self.video_player.pause()
        else:
            if self.timeline.position_seconds >= self._song.duration_seconds - 0.05:
                self._seek_timeline(0.0)
            if self._preview_path:
                self._set_video_position(round(self.timeline.position_seconds * 1000))
                self.video_player.play()
            self.media_player.play()
            if self._preview_path:
                self._video_sync_timer.start()

    @Slot(float)
    def _seek_timeline(self, seconds: float) -> None:
        self._pending_playhead_seconds = max(0.0, seconds)
        self.timeline.set_position(seconds)
        self._update_timecode(seconds)
        if self._song and self._song.path.is_file():
            self.media_player.setPosition(round(seconds * 1000))
        if self._preview_path:
            self._set_video_position(round(seconds * 1000))

    @Slot(int)
    def _playback_position_changed(self, milliseconds: int) -> None:
        seconds = milliseconds / 1000.0
        self.timeline.set_position(seconds)
        self._update_timecode(seconds)

    @Slot()
    def _sync_video_once(self) -> None:
        if (
            not self._preview_path
            or self.media_player.playbackState() is not QMediaPlayer.PlaybackState.PlayingState
            or self.video_player.playbackState() is not QMediaPlayer.PlaybackState.PlayingState
        ):
            return
        audio_position = self.media_player.position()
        if abs(self.video_player.position() - audio_position) > 750:
            self.video_player.setPosition(audio_position)

    def _set_video_position(self, milliseconds: int) -> None:
        if abs(self.video_player.position() - milliseconds) > 40:
            self.video_player.setPosition(milliseconds)

    @Slot(QMediaPlayer.PlaybackState)
    def _playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        self.play_button.setText(
            "PAUSE" if state is QMediaPlayer.PlaybackState.PlayingState else "PLAY"
        )
        if not self._preview_path:
            return
        if state is QMediaPlayer.PlaybackState.PlayingState:
            self.video_player.play()
        elif state is QMediaPlayer.PlaybackState.PausedState:
            self._video_sync_timer.stop()
            self.video_player.pause()
        else:
            self._video_sync_timer.stop()
            self.video_player.stop()

    @Slot(QMediaPlayer.MediaStatus)
    def _media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self.media_player.setPosition(round(self._pending_playhead_seconds * 1000))

    @Slot(QMediaPlayer.MediaStatus)
    def _video_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ):
            self._set_video_position(round(self._pending_playhead_seconds * 1000))
            self.preview_stack.setCurrentIndex(1)
            if self.media_player.playbackState() is QMediaPlayer.PlaybackState.PlayingState:
                self.video_player.play()
                self._video_sync_timer.start()

    @Slot(object, str)
    def _video_playback_failed(self, _error: object, message: str) -> None:
        if not self._preview_path:
            return
        self.preview_stack.setCurrentIndex(0)
        self.preview_eyebrow.setText("PREVIEW COULD NOT PLAY")
        self.preview_title.setText("The edit exists,\nbut playback failed.")
        self.preview_body.setText(message or "The local video backend could not open the proxy.")
        self.task_title.setText("PREVIEW PLAYBACK NEEDS ATTENTION")
        self.task_detail.setText(message or "The local video backend could not open the proxy")

    def _set_song_playback_source(self, position_seconds: float = 0.0) -> None:
        self.media_player.stop()
        self._pending_playhead_seconds = position_seconds
        if self._song and self._song.path.is_file():
            self.media_player.setSource(QUrl.fromLocalFile(str(self._song.path.resolve())))
        else:
            self.media_player.setSource(QUrl())

    def _set_video_preview_source(self, path: Path | None, position_seconds: float = 0.0) -> None:
        self.video_player.stop()
        self.video_widget.clear()
        self._preview_path = path.resolve() if path else None
        self._pending_playhead_seconds = position_seconds
        if self._preview_path and self._preview_path.is_file():
            self.video_player.setSource(QUrl.fromLocalFile(str(self._preview_path)))
            self._set_video_position(round(position_seconds * 1000))
            self.preview_stack.setCurrentIndex(1)
        else:
            self.video_player.setSource(QUrl())
            self.preview_stack.setCurrentIndex(0)

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
        initial_detail: str = "Preparing local processing",
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
        self._task_failed_message = None
        self.task_title.setText(title)
        self.task_detail.setText(initial_detail)
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
        self._generated_timeline = None
        self._set_video_preview_source(None)
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
        self._generated_timeline = None
        self._set_video_preview_source(None)
        self.timeline.set_analysis(result)
        self.timeline.set_first_cut(None)
        self.timeline_meta.setText(f"{len(result.events)} EVENTS · {result.model_name.upper()}")
        self.preview_eyebrow.setText("STRUCTURE READY")
        self.preview_title.setText("Now bring in\nthe footage.")
        self.preview_body.setText(
            "The detected events are ready for mappings, clip generation, "
            "locking, and regeneration."
        )
        self._set_dirty(True)

    @Slot(object)
    def _video_edit_ready(self, result: object) -> None:
        assert isinstance(result, VideoEditPreview)
        self._generated_timeline = result.timeline
        self.timeline.set_first_cut(result.timeline)
        event_count = len(self._analysis.events) if self._analysis else 0
        self.timeline_meta.setText(f"{len(result.timeline.clips)} EDITS · {event_count} EVENTS")
        self._set_video_preview_source(result.path, self.timeline.position_seconds)
        self.task_title.setText("VIDEO EDIT READY")
        self.task_detail.setText(
            f"{len(result.timeline.clips)} edits · {result.effect_count} effect hits · "
            f"{result.width} × {result.height} preview"
        )
        self.task_progress.setValue(100)
        self.generate_button.setText("Regenerate video edit")
        self._set_dirty(True)

    @Slot(str)
    def _task_failed(self, message: str) -> None:
        self._task_failed_message = message
        self.task_title.setText("TASK NEEDS ATTENTION")
        self.task_detail.setText(message)
        self.task_progress.setValue(0)
        self.generate_button.setText(
            "Regenerate video edit" if self._generated_timeline else "Generate video edit"
        )
        QMessageBox.warning(self, "Kinebeat could not continue", message)

    @Slot()
    def _task_finished(self) -> None:
        self._task_thread = None
        self._task_worker = None
        if self._task_failed_message:
            self._sync_state()
            return
        if self._preview_path and self._generated_timeline:
            self.task_title.setText("VIDEO EDIT READY")
            self.task_detail.setText(
                f"{len(self._generated_timeline.clips)} beat-synced edits · playable preview ready"
            )
            self.task_progress.setValue(100)
            self.generate_button.setText("Regenerate video edit")
        elif self._generated_timeline:
            self.task_title.setText("EDIT DECISIONS READY")
            self.task_detail.setText("Generate the video edit to build its playable preview")
            self.task_progress.setValue(100)
        elif self._analysis:
            self.task_title.setText("STRUCTURE READY")
            self.task_detail.setText(
                "Generate the video edit"
                if self._verified_video_paths()
                else "Import usable footage to continue"
            )
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
        verified_paths = self._verified_video_paths()
        media_checking = bool(self._video_paths) and (
            len(verified_paths) + len(self._broken_video_paths()) < len(self._video_paths)
        )
        self.choose_music_button.setDisabled(busy)
        self.analyse_button.setEnabled(self._song is not None and not busy)
        self.footage_button.setEnabled(self._analysis is not None and not busy)
        for row in self._media_rows:
            row.remove_button.setEnabled(not busy)
        self.strategy_combo.setEnabled(self._analysis is not None and not busy)
        for combo in self.mapping_combos.values():
            combo.setEnabled(self._analysis is not None and not busy)
        self.generate_button.setEnabled(
            self._analysis is not None and bool(verified_paths) and not media_checking and not busy
        )
        if not busy:
            if media_checking:
                self.generate_button.setText("Checking video clips…")
            elif self._video_paths and not verified_paths:
                self.generate_button.setText("No usable video clips")
            else:
                self.generate_button.setText(
                    "Regenerate video edit" if self._generated_timeline else "Generate video edit"
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
        self._generated_timeline = None
        self._set_video_preview_source(None)
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
            "Import clips to generate a complete video edit."
        )
        self.task_title.setText("STRUCTURE READY")
        self.task_detail.setText("Import footage to generate the video edit")
        self.task_progress.setValue(100)
        self._set_dirty(False)
        self._sync_state()
