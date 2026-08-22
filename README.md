# Kinebeat

Kinebeat is a local-first music-driven video editor. It analyses a song, creates an
editable first-cut timeline from imported footage, and lets creators keep the good
parts while regenerating everything else.

## Product direction

1. Load a song and analyse its musical structure automatically.
2. Import video clips and generate a complete beat-driven edit.
3. Lock clips, effects, or ranges that should remain unchanged.
4. Drag clips into a different order or regenerate any unlocked selection.
5. Map detected musical events such as kicks, snares, hi-hats, bass, and vocals to
   cuts and short visual effects.
6. Preview and export locally.

The initial desktop application will follow the proven Chronophoto conventions:
Python, PySide6, processing separated from Qt, cancellable background work, source-
resolution export, CPU fallbacks, automated tests, PyInstaller packaging, and GitHub
Actions.

## Status

The current runnable slice covers local music import, waveform extraction, automatic
six-stem separation through Demucs, musical-event detection, multi-clip video import,
editable per-instrument action mappings, kick-aligned first-cut generation with visible
background progress, music playback with timeline seeking, and versioned `.kinebeat`
project save/load. Generated edit decisions are preserved while media remains external
to the small project document. See
[the confirmed design brief](docs/DESIGN_BRIEF.md).

## Development

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m kinebeat
```

`run.bat` and `run.sh` install the complete local analysis runtime automatically. For
manual environment setup, install the analysis and development extras together:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[analysis,dev]"
```

The first analysis downloads the selected Demucs model. After that, separation and
event detection run locally.

Build a development package with `build.bat` on Windows or `./build.sh` on macOS and
Linux. The current package contains the editor foundation; bundling the much larger
analysis runtime will be qualified separately before the first release.

## License

MIT
