from __future__ import annotations

STYLESHEET = """
QWidget {
    background: #0a0b0a;
    color: #e5e7e2;
    font-family: "__APP_FONT__";
    font-size: 13px;
}
QMainWindow { background: #090a09; }
QLabel { background: transparent; }
QFrame#appHeader {
    background: #0d0e0d;
    border-bottom: 1px solid #30332f;
}
QLabel#wordmark {
    color: #f0f1ed;
    font-family: "__APP_FONT__";
    font-size: 23px;
    font-weight: 700;
    letter-spacing: 3px;
}
QLabel#strapline, QLabel#eyebrow, QLabel#fieldLabel {
    color: #7f847f;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.4px;
}
QFrame#setupRail {
    background: #0e0f0e;
    border-right: 1px solid #30332f;
}
QFrame#inspector {
    background: #0e0f0e;
    border-left: 1px solid #30332f;
}
QFrame#stepSection { border-bottom: 1px solid #292c29; }
QScrollArea#mediaLibraryScroll, QWidget#mediaLibraryContent {
    background: transparent;
    border: none;
}
QFrame#mediaLibraryRow {
    background: #141614;
    border: 1px solid #2d302d;
    border-radius: 2px;
}
QFrame#mediaLibraryRow:hover { background: #181a18; border-color: #494d48; }
QFrame#mediaLibraryRow[missing="true"] { border-color: #6b504b; }
QLabel#mediaName { color: #dfe2dc; font-size: 11px; font-weight: 600; }
QLabel#mediaMeta { color: #686d67; font-size: 9px; letter-spacing: 0.8px; }
QLabel#mediaThumbnail {
    color: #656a64;
    background: #090a09;
    border: 1px solid #30332f;
    font-size: 8px;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QLabel#mediaThumbnail[state="unavailable"] {
    color: #735b55;
    background: #14100f;
    border-color: #513e39;
}
QLabel#mediaThumbnail[state="ready"] { border-color: #3c403b; }
QLabel#mediaEmptyState {
    color: #666b65;
    font-size: 11px;
    padding: 22px 12px;
}
QPushButton#mediaRemoveButton {
    min-height: 26px;
    max-height: 26px;
    color: #777c76;
    background: transparent;
    border: 1px solid transparent;
    padding: 0 5px;
    font-size: 9px;
    letter-spacing: 0.5px;
}
QPushButton#mediaRemoveButton:hover {
    color: #eee3df;
    background: #29201e;
    border-color: #6b504b;
}
QPushButton#mediaRemoveButton:disabled { color: #454944; background: transparent; }
QLabel#stepNumber {
    color: #5f645f;
    font-family: "__APP_FONT__";
    font-size: 26px;
    font-weight: 700;
}
QLabel#sectionTitle {
    color: #e8eae5;
    font-size: 16px;
    font-weight: 700;
}
QLabel#bodyMuted { color: #858a84; font-size: 12px; }
QLabel#sourceName { color: #e4e6e1; font-weight: 700; }
QLabel#sourceMeta { color: #898e88; font-size: 11px; }
QFrame#dropZone {
    background: #121412;
    border: 1px dashed #555a54;
    border-radius: 2px;
}
QFrame#dropZone[dragActive="true"] {
    background: #1b1e1a;
    border: 1px solid #e0e3dc;
}
QLabel#dropTitle { color: #dfe1dc; font-size: 12px; font-weight: 700; }
QLabel#dropHint { color: #757a74; font-size: 10px; }
QPushButton {
    min-height: 36px;
    border-radius: 2px;
    padding: 0 13px;
    font-weight: 600;
}
QPushButton#primaryButton {
    min-height: 42px;
    color: #10110f;
    background: #e8eae4;
    border: 1px solid #e8eae4;
}
QPushButton#primaryButton:hover { background: #f4f5f1; border-color: #f4f5f1; }
QPushButton#secondaryButton, QPushButton#quietButton {
    color: #c9ccc6;
    background: #171917;
    border: 1px solid #4a4e49;
}
QPushButton#transportButton {
    min-height: 28px;
    color: #10110f;
    background: #dfe2db;
    border: 1px solid #dfe2db;
    font-size: 10px;
    letter-spacing: 0.8px;
}
QPushButton#transportButton:hover { background: #f2f4ee; border-color: #f2f4ee; }
QPushButton#transportButton:disabled {
    color: #555a54;
    background: #171917;
    border-color: #292c29;
}
QPushButton#secondaryButton:hover, QPushButton#quietButton:hover {
    color: #f0f2ed;
    background: #202320;
    border-color: #858a84;
}
QPushButton#quietButton[saveState="saved"] {
    color: #101510;
    background: #cbdcc8;
    border-color: #cbdcc8;
}
QPushButton:focus { border: 1px solid #f2f4ee; }
QPushButton:disabled {
    color: #555a54;
    background: #121312;
    border-color: #292c29;
}
QPushButton#primaryButton:disabled {
    color: #555a54;
    background: #171917;
    border-color: #292c29;
}
QFrame#previewSurface {
    background: #070807;
    border-bottom: 1px solid #30332f;
}
QStackedWidget#previewStack, QWidget#videoPreview { background: #070807; }
QLabel#previewTitle {
    color: #f0f2ed;
    font-family: "__APP_FONT__";
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 1px;
}
QLabel#previewBody { color: #858a84; font-size: 13px; }
QFrame#timelineHeader { background: #111311; border-bottom: 1px solid #30332f; }
QLabel#timelineTitle { color: #dcdfd9; font-size: 13px; font-weight: 700; }
QLabel#timelineMeta { color: #747974; font-size: 10px; letter-spacing: 1px; }
QComboBox {
    min-height: 34px;
    color: #d4d7d1;
    background: #151715;
    border: 1px solid #414540;
    border-radius: 2px;
    padding: 0 9px;
}
QComboBox:focus { border-color: #e3e6df; }
QComboBox:disabled { color: #545953; border-color: #292c29; }
QComboBox QAbstractItemView {
    color: #dfe1dc;
    background: #151715;
    selection-color: #10110f;
    selection-background-color: #e4e6e0;
}
QFrame#mappingRow { border-bottom: 1px solid #262926; }
QLabel#mappingInstrument { color: #d9dcd6; font-size: 11px; font-weight: 700; }
QComboBox#mappingCombo {
    min-height: 28px;
    color: #b9bdb7;
    background: #131513;
    border-color: #343834;
    font-size: 10px;
}
QFrame#taskBar {
    background: #111311;
    border-top: 1px solid #30332f;
}
QLabel#taskTitle { color: #dcdfd9; font-size: 11px; font-weight: 700; }
QLabel#taskDetail { color: #7e837d; font-size: 10px; }
QProgressBar {
    height: 3px;
    background: #30332f;
    border: none;
}
QProgressBar::chunk { background: #dfe2db; }
QSplitter::handle { background: #30332f; width: 1px; }
QToolTip {
    color: #e4e6e1;
    background: #191b19;
    border: 1px solid #555a54;
    padding: 6px;
}
"""
