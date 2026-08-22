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

Product discovery and repository foundation. See
[the draft design brief](docs/DESIGN_BRIEF.md).

## License

MIT
