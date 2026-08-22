from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

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
