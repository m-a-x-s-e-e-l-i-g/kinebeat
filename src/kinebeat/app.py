from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from kinebeat import __version__
from kinebeat.ui import KinebeatWindow
from kinebeat.ui.style import STYLESHEET


def load_application_font() -> QFont:
    candidates = (
        Path("C:/Windows/Fonts/bahnschrift.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if not candidate.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(candidate))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            return QFont(families[0], 10)
    return QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))


def application_stylesheet(font: QFont) -> str:
    return STYLESHEET.replace("__APP_FONT__", font.family())


def main() -> int:
    if "--version" in sys.argv:
        print(f"Kinebeat {__version__}")
        return 0
    app = QApplication(sys.argv)
    app.setApplicationName("Kinebeat")
    app.setOrganizationName("Kinebeat")
    app.setApplicationVersion(__version__)
    font = load_application_font()
    app.setFont(font)
    app.setStyleSheet(application_stylesheet(font))
    window = KinebeatWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
