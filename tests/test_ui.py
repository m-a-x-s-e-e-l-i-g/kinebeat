from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from kinebeat.domain import EffectAction, EventKind, InstrumentMapping, ProjectState
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
