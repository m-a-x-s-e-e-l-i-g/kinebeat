from __future__ import annotations

import argparse
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from kinebeat.app import application_stylesheet, load_application_font
from kinebeat.processing import generate_first_cut
from kinebeat.ui.window import KinebeatWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a Kinebeat UI verification image.")
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--state",
        choices=("empty", "analysed", "generated", "broken", "saved"),
        default="analysed",
    )
    args = parser.parse_args()
    app = QApplication([])
    font = load_application_font()
    app.setFont(font)
    app.setStyleSheet(application_stylesheet(font))
    window = KinebeatWindow()
    window.resize(1480, 900)
    if args.state in ("analysed", "generated", "broken", "saved"):
        window.load_demo_state()
    if args.state in ("generated", "broken"):
        window._video_paths = (
            Path("city-wide-establishing-shot.mp4"),
            Path("close-motion.mp4"),
            Path("night-drive-reflections-and-rain.mov"),
        )
        window._update_footage_copy()
        thumbnail_colors = ("#aa4b2c", "#45654b", "#394f79")
        for index, (row, color) in enumerate(
            zip(window._media_rows, thumbnail_colors, strict=True)
        ):
            if args.state == "broken" and index == 2:
                window._media_thumbnail_failed(
                    row.path, "Invalid data found when processing input."
                )
                continue
            thumbnail = QImage(72, 45, QImage.Format.Format_RGB888)
            thumbnail.fill(QColor(color))
            window._media_thumbnail_ready(row.path, thumbnail)
        if args.state == "generated":
            result = generate_first_cut(
                window._analysis,
                window._video_paths,
                strategy="Import order",
                seed=42,
                progress=lambda *_: None,
                cancelled=lambda: False,
            )
            window._generated_timeline = result
            window.timeline.set_first_cut(result)
            window.timeline_meta.setText(
                f"{len(result.clips)} EDITS · {len(window._analysis.events)} EVENTS"
            )
        window._sync_state()
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
