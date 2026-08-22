from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

from kinebeat.domain import EffectAction, EventKind, InstrumentMapping, ProjectState
from kinebeat.processing import VideoEditPreview, generate_first_cut
from kinebeat.ui import window as window_module
from kinebeat.ui.window import KinebeatWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_first_run_guides_song_first_flow() -> None:
    _app()
    window = KinebeatWindow()

    assert window.analyse_button.isEnabled() is False
    assert window.footage_button.isEnabled() is False
    assert window.generate_button.isEnabled() is False
    assert window.preview_title.text() == "Your song sets\nthe timeline."
    assert all(label.text() != "LOCAL PROCESSING" for label in window.findChildren(QLabel))
    window.close()


def test_demo_analysis_unlocks_footage_but_not_generation() -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()

    assert window.analyse_button.isEnabled() is True
    assert window.footage_button.isEnabled() is True
    assert window.strategy_combo.isEnabled() is True
    assert window.generate_button.isEnabled() is False
    assert "EVENTS" in window.timeline_meta.text()
    assert window.mapping_combos[EventKind.KICK].currentData() == EffectAction.CUT.value
    assert window.mapping_combos[EventKind.SNARE].currentData() == EffectAction.RANDOM_EFFECT.value
    assert window.mapping_combos[EventKind.BASS].currentData() == EffectAction.ADD_INTENSITY.value
    assert window.mapping_combos[EventKind.VOCAL].currentData() == EffectAction.ADD_AMBIANCE.value
    window.close()


def test_import_video_button_adds_clips_and_unlocks_generation(tmp_path, monkeypatch) -> None:
    _app()
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mov"
    first.touch()
    second.touch()
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(first), str(second), str(first)], ""),
    )
    window = KinebeatWindow()
    window.load_demo_state()

    window.footage_button.click()

    assert window._video_paths == (first.resolve(), second.resolve())
    assert window.generate_button.isEnabled() is True
    assert "2 clips imported" in window.footage_copy.text()
    window.close()


def test_generate_video_edit_reports_progress_and_draws_edits(tmp_path, monkeypatch) -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    window._video_paths = (tmp_path / "one.mp4", tmp_path / "two.mp4")
    window._sync_state()
    progress: list[tuple[int, str]] = []

    def fake_preview(analysis, video_paths, *, strategy, seed, output_path, progress, cancelled):
        timeline = generate_first_cut(
            analysis,
            video_paths,
            strategy=strategy,
            seed=seed,
            progress=progress,
            cancelled=cancelled,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return VideoEditPreview(timeline, output_path, 640, 360, 24)

    def run_immediately(*, task, on_success, **_kwargs) -> None:
        result = task(
            progress=lambda value, detail: progress.append((value, detail)),
            cancelled=lambda: False,
        )
        on_success(result)

    monkeypatch.setattr(window, "_start_task", run_immediately)
    monkeypatch.setattr(window_module, "generate_video_edit_preview", fake_preview)
    monkeypatch.setattr(
        window,
        "_set_video_preview_source",
        lambda path, position_seconds=0.0: setattr(window, "_preview_path", path),
    )

    window.generate_button.click()

    assert window._generated_timeline is not None
    assert window.timeline._first_cut is window._generated_timeline
    assert window.task_title.text() == "VIDEO EDIT READY"
    assert window.task_progress.value() == 100
    assert window.generate_button.text() == "Regenerate video edit"
    assert "beat-synced edits" in window.task_detail.text()
    assert progress[0] == (5, "Finding kick cut points")
    assert progress[-1][0] == 100
    assert window._preview_path is not None
    window.close()


def test_generate_button_runs_background_video_edit(tmp_path, monkeypatch) -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    window._video_paths = (tmp_path / "one.mp4", tmp_path / "two.mp4")
    window._sync_state()

    def fake_preview(analysis, video_paths, *, strategy, seed, output_path, progress, cancelled):
        timeline = generate_first_cut(
            analysis,
            video_paths,
            strategy=strategy,
            seed=seed,
            progress=progress,
            cancelled=cancelled,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return VideoEditPreview(timeline, output_path, 640, 360, 24)

    monkeypatch.setattr(window_module, "generate_video_edit_preview", fake_preview)
    monkeypatch.setattr(
        window,
        "_set_video_preview_source",
        lambda path, position_seconds=0.0: setattr(window, "_preview_path", path),
    )

    window.generate_button.click()
    loop = QEventLoop()
    if window._task_thread is not None:
        window._task_thread.finished.connect(loop.quit)
        QTimer.singleShot(5000, loop.quit)
        loop.exec()

    assert window._task_thread is None
    assert window._generated_timeline is not None
    assert window.task_title.text() == "VIDEO EDIT READY"
    assert window.task_progress.value() == 100
    assert window.generate_button.text() == "Regenerate video edit"
    assert window._preview_path is not None
    window.close()


def test_project_application_restores_timeline_and_strategy(tmp_path, monkeypatch) -> None:
    _app()
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    window = KinebeatWindow()
    window.load_demo_state()
    state = ProjectState(
        song=window._song,
        analysis=window._analysis,
        video_paths=(tmp_path / "clip.mp4",),
        footage_strategy="Least used first",
        playhead_seconds=42.5,
        effect_mappings=(
            InstrumentMapping(EventKind.KICK, EffectAction.TIME_BEND),
            InstrumentMapping(EventKind.SNARE, EffectAction.NO_ACTION),
        ),
    )

    window._apply_project(tmp_path / "restored.kinebeat", state)

    assert window.strategy_combo.currentText() == "Least used first"
    assert window.timeline.position_seconds == 42.5
    assert window.timecode_label.text() == "0:42 / 2:54"
    assert window.generate_button.isEnabled() is True
    assert window.mapping_combos[EventKind.KICK].currentData() == EffectAction.TIME_BEND.value
    assert window.mapping_combos[EventKind.SNARE].currentData() == EffectAction.NO_ACTION.value
    window.close()


def test_mapping_selector_updates_project_state() -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    snare = window.mapping_combos[EventKind.SNARE]

    snare.setCurrentIndex(snare.findData(EffectAction.ADD_AMBIANCE.value))

    mapping_by_instrument = {
        mapping.instrument: mapping.action for mapping in window._project_state().effect_mappings
    }
    assert mapping_by_instrument[EventKind.SNARE] is EffectAction.ADD_AMBIANCE
    assert window.isWindowModified() is True
    window.close()


def test_clicking_timeline_moves_playhead() -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    window.timeline.resize(1000, 250)

    QTest.mouseClick(
        window.timeline,
        Qt.MouseButton.LeftButton,
        pos=QPoint(532, 100),
    )

    assert 86.5 < window.timeline.position_seconds < 87.5
    assert window.timecode_label.text() == "1:27 / 2:54"
    window.close()


def test_aligned_video_position_does_not_trigger_redundant_seek(monkeypatch) -> None:
    _app()
    window = KinebeatWindow()
    seeks: list[int] = []
    monkeypatch.setattr(window.video_player, "position", lambda: 0)
    monkeypatch.setattr(window.video_player, "setPosition", seeks.append)

    window._set_video_position(0)
    window._set_video_position(1000)

    assert seeks == [1000]
    window.close()


def test_save_feedback_has_reduced_motion_fallback(tmp_path) -> None:
    _app()
    window = KinebeatWindow(animations_enabled=False)
    window.load_demo_state()
    window._project_path = tmp_path / "edit.kinebeat"

    window._save_project()

    assert window.save_project_button.text() == "Saved"
    assert window.save_project_button.property("saveState") == "saved"
    assert window._save_feedback_effect.opacity() == 1.0

    window._begin_save_feedback_reset()

    assert window.save_project_button.text() == "Save project"
    assert window.save_project_button.property("saveState") == "idle"
    window.close()


def test_save_feedback_animates_and_returns_to_idle(tmp_path) -> None:
    _app()
    window = KinebeatWindow(animations_enabled=True)
    window.load_demo_state()
    window._project_path = tmp_path / "edit.kinebeat"

    window._save_project()
    QTest.qWait(260)

    assert window.save_project_button.text() == "Saved"
    assert window._save_feedback_effect.opacity() > 0.99

    window._begin_save_feedback_reset()
    QTest.qWait(300)

    assert window.save_project_button.text() == "Save project"
    assert window._save_feedback_effect.opacity() > 0.99
    window.close()
