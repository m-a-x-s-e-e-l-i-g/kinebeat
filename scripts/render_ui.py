from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from kinebeat.app import application_stylesheet, load_application_font
from kinebeat.ui.window import KinebeatWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Kinebeat UI verification image.")
    parser.add_argument("output", type=Path)
    parser.add_argument("--state", choices=("empty", "analysed", "saved"), default="analysed")
    args = parser.parse_args()
    app = QApplication([])
    font = load_application_font()
    app.setFont(font)
    app.setStyleSheet(application_stylesheet(font))
    window = KinebeatWindow()
    window.resize(1480, 900)
    if args.state in ("analysed", "saved"):
        window.load_demo_state()
    if args.state == "saved":
        window._show_save_feedback()
    window.show()

    def capture() -> None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if not window.grab().save(str(args.output)):
            raise RuntimeError(f"Could not save verification image to {args.output}")
        app.quit()

    QTimer.singleShot(150, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
