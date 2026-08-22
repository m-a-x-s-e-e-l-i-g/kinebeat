from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from kinebeat.domain import ProjectState
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
    )

    window._apply_project(tmp_path / "restored.kinebeat", state)

    assert window.strategy_combo.currentText() == "Least used first"
    assert window.timeline.position_seconds == 42.5
    assert window.timecode_label.text() == "0:42 / 2:54"
    assert window.generate_button.isEnabled() is True
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
