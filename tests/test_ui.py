from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtCore import QEventLoop, QPoint, Qt, QTimer
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QLabel, QMessageBox

from kinebeat.domain import (
    EffectAction,
    EventKind,
    GeneratedTimeline,
    InstrumentMapping,
    ProjectState,
    TimelineClip,
)
from kinebeat.processing import VideoEditPreview, VideoMediaCheck, generate_first_cut
from kinebeat.ui import window as window_module
from kinebeat.ui.window import KinebeatWindow


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _valid_media_check(_path: Path) -> VideoMediaCheck:
    pixels = np.full((45, 72, 3), (210, 70, 25), dtype=np.uint8)
    return VideoMediaCheck(pixels, 5.0)


def _wait_for_media_checks(window: KinebeatWindow) -> None:
    for _ in range(100):
        _app().processEvents()
        if not window._thumbnail_tasks:
            return
        QTest.qWait(10)
    raise AssertionError("Media checks did not finish")


def _mark_media_ready(window: KinebeatWindow, *paths: Path) -> None:
    image = QImage(72, 45, QImage.Format.Format_RGB888)
    image.fill(Qt.GlobalColor.red)
    for path in paths:
        window._media_thumbnail_ready(path.resolve(), image)


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
    for action in (
        EffectAction.GLITCH,
        EffectAction.VHS,
        EffectAction.SILHOUETTE_STRETCH,
        EffectAction.VIDEO_VOLUME,
        EffectAction.DATAMOSH,
    ):
        assert window.mapping_combos[EventKind.SNARE].findData(action.value) >= 0
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
    monkeypatch.setattr(window_module, "inspect_video_media", _valid_media_check)
    window = KinebeatWindow()
    window.load_demo_state()

    window.footage_button.click()

    assert window._video_paths == (first.resolve(), second.resolve())
    assert window.generate_button.isEnabled() is False
    _wait_for_media_checks(window)
    assert window.generate_button.isEnabled() is True
    assert window.footage_copy.text() == "2 ready"
    assert [row.path for row in window._media_rows] == [first.resolve(), second.resolve()]
    window.close()


def test_media_library_removes_an_imported_video(tmp_path, monkeypatch) -> None:
    _app()
    first = (tmp_path / "first.mp4").resolve()
    second = (tmp_path / "second.mov").resolve()
    first.touch()
    second.touch()
    monkeypatch.setattr(window_module, "inspect_video_media", _valid_media_check)
    window = KinebeatWindow()
    window.load_demo_state()
    window._video_paths = (first, second)
    window._update_footage_copy()
    _wait_for_media_checks(window)
    window._sync_state()

    window._media_rows[0].remove_button.click()

    assert window._video_paths == (second,)
    assert [row.path for row in window._media_rows] == [second]
    assert window.footage_copy.text() == "1 ready"
    assert window.isWindowModified() is True
    window.close()


def test_media_library_loads_video_thumbnails_without_blocking(tmp_path, monkeypatch) -> None:
    _app()
    source = (tmp_path / "thumbnail.mp4").resolve()
    source.touch()
    monkeypatch.setattr(window_module, "inspect_video_media", _valid_media_check)
    window = KinebeatWindow()
    window.load_demo_state()
    window._video_paths = (source,)
    window._update_footage_copy()

    _wait_for_media_checks(window)

    row = window._media_rows[0]
    assert row.thumbnail.property("state") == "ready"
    assert row.thumbnail.pixmap().isNull() is False
    window.close()


def test_broken_import_is_marked_and_excluded_from_generation(tmp_path, monkeypatch) -> None:
    _app()
    ready = (tmp_path / "ready.mp4").resolve()
    broken = (tmp_path / "broken.mp4").resolve()
    ready.touch()
    broken.touch()

    def inspect(path: Path) -> VideoMediaCheck:
        if path.name == "broken.mp4":
            raise ValueError("Invalid data found when processing input.")
        return _valid_media_check(path)

    monkeypatch.setattr(window_module, "inspect_video_media", inspect)
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileNames",
        lambda *args, **kwargs: ([str(ready), str(broken)], ""),
    )
    window = KinebeatWindow()
    window.load_demo_state()

    window.footage_button.click()
    _wait_for_media_checks(window)

    ready_row, broken_row = window._media_rows
    assert ready_row.property("health") == "ready"
    assert broken_row.property("health") == "broken"
    assert broken_row.thumbnail.text() == "BROKEN"
    assert broken_row.meta.text().endswith("· BROKEN")
    assert "Invalid data" in broken_row.toolTip()
    assert window._verified_video_paths() == (ready,)
    assert window.generate_button.isEnabled() is True
    assert window.footage_copy.text() == "1 ready · 1 broken"
    window.close()


def test_removing_used_video_invalidates_generated_preview(tmp_path, monkeypatch) -> None:
    _app()
    used = (tmp_path / "used.mp4").resolve()
    remaining = (tmp_path / "remaining.mp4").resolve()
    used.touch()
    remaining.touch()
    window = KinebeatWindow()
    monkeypatch.setattr(window, "_set_video_preview_source", lambda *_: None)
    window.load_demo_state()
    timeline = GeneratedTimeline((TimelineClip(used, 0.0, 1.0),), seed=4)
    window._video_paths = (used, remaining)
    window._generated_timeline = timeline
    window.timeline.set_first_cut(timeline)
    window._update_footage_copy()
    _mark_media_ready(window, used, remaining)

    window._media_rows[0].remove_button.click()

    assert window._video_paths == (remaining,)
    assert window._generated_timeline is None
    assert window.timeline._first_cut is None
    assert window.generate_button.isEnabled() is True
    assert window.task_title.text() == "VIDEO EDIT NEEDS REBUILDING"
    window.close()


def test_removing_final_used_video_returns_to_library_empty_state(tmp_path, monkeypatch) -> None:
    _app()
    used = (tmp_path / "only.mp4").resolve()
    used.touch()
    window = KinebeatWindow()
    monkeypatch.setattr(window, "_set_video_preview_source", lambda *_: None)
    window.load_demo_state()
    timeline = GeneratedTimeline((TimelineClip(used, 0.0, 1.0),), seed=5)
    window._video_paths = (used,)
    window._generated_timeline = timeline
    window.timeline.set_first_cut(timeline)
    window._update_footage_copy()

    window._media_rows[0].remove_button.click()

    assert window._video_paths == ()
    assert window.generate_button.isEnabled() is False
    assert window.task_title.text() == "MEDIA LIBRARY EMPTY"
    assert window.preview_title.text() == "Add footage to\nrebuild the edit."
    window.close()


def test_generate_video_edit_reports_progress_and_draws_edits(tmp_path, monkeypatch) -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    ready_paths = (tmp_path / "one.mp4", tmp_path / "two.mp4")
    broken_path = tmp_path / "broken.mp4"
    window._video_paths = ready_paths + (broken_path,)
    _mark_media_ready(window, *ready_paths)
    window._media_thumbnail_failed(broken_path, "Invalid video data")
    window._sync_state()
    progress: list[tuple[int, str]] = []

    def fake_preview(
        analysis,
        video_paths,
        *,
        strategy,
        seed,
        output_path,
        progress,
        cancelled,
        effect_mappings,
        source_durations,
    ):
        del effect_mappings
        assert video_paths == ready_paths
        assert source_durations == {path: 1.0 for path in ready_paths}
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
    assert "effect hits" in window.task_detail.text()
    assert progress[0] == (5, "Finding kick cut points")
    assert progress[-1][0] == 100
    assert window._preview_path is not None
    window.close()


def test_generate_button_runs_background_video_edit(tmp_path, monkeypatch) -> None:
    _app()
    window = KinebeatWindow()
    window.load_demo_state()
    window._video_paths = (tmp_path / "one.mp4", tmp_path / "two.mp4")
    _mark_media_ready(window, *window._video_paths)
    window._sync_state()

    def fake_preview(
        analysis,
        video_paths,
        *,
        strategy,
        seed,
        output_path,
        progress,
        cancelled,
        effect_mappings,
        source_durations,
    ):
        del effect_mappings, source_durations
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
    source = tmp_path / "clip.mp4"
    source.touch()
    monkeypatch.setattr(window_module, "inspect_video_media", _valid_media_check)
    state = ProjectState(
        song=window._song,
        analysis=window._analysis,
        video_paths=(source,),
        footage_strategy="Least used first",
        playhead_seconds=42.5,
        effect_mappings=(
            InstrumentMapping(EventKind.KICK, EffectAction.TIME_BEND),
            InstrumentMapping(EventKind.SNARE, EffectAction.NO_ACTION),
        ),
    )

    window._apply_project(tmp_path / "restored.kinebeat", state)
    _wait_for_media_checks(window)

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
