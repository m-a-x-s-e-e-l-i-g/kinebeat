from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kinebeat.domain.music import (
    EventKind,
    MusicalEvent,
    MusicAnalysis,
    SongMetadata,
    StemArtifact,
)

PROJECT_FORMAT = "kinebeat-project"
PROJECT_VERSION = 1


class ProjectFormatError(ValueError):
    """Raised when a file is not a supported Kinebeat project."""


@dataclass(frozen=True, slots=True)
class ProjectState:
    song: SongMetadata | None = None
    analysis: MusicAnalysis | None = None
    video_paths: tuple[Path, ...] = ()
    footage_strategy: str = "Movement based"
    playhead_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.analysis and not self.song:
            raise ValueError("analysis requires a song")
        if self.playhead_seconds < 0:
            raise ValueError("playhead_seconds must be non-negative")


def save_project(path: Path, state: ProjectState) -> None:
    """Atomically save a project while keeping media files external."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _state_to_dict(state, path.parent)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def load_project(path: Path) -> ProjectState:
    path = path.resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectFormatError(f"Could not read this project: {error}") from error
    if not isinstance(payload, dict):
        raise ProjectFormatError("The project root must be an object.")
    if payload.get("format") != PROJECT_FORMAT:
        raise ProjectFormatError("This is not a Kinebeat project file.")
    if payload.get("version") != PROJECT_VERSION:
        raise ProjectFormatError(f"Project version {payload.get('version')!r} is not supported.")
    try:
        return _state_from_dict(payload, path.parent)
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectFormatError(f"The project data is incomplete: {error}") from error


def _state_to_dict(state: ProjectState, base: Path) -> dict[str, Any]:
    song = state.song
    analysis = state.analysis
    return {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "song": (
            {
                "path": _store_path(song.path, base),
                "duration_seconds": song.duration_seconds,
                "sample_rate": song.sample_rate,
                "channels": song.channels,
                "codec": song.codec,
                "waveform_peaks": list(song.waveform_peaks),
            }
            if song
            else None
        ),
        "analysis": (
            {
                "model_name": analysis.model_name,
                "stems": [
                    {"name": stem.name, "path": _store_path(stem.path, base)}
                    for stem in analysis.stems
                ],
                "events": [
                    {
                        "kind": event.kind.value,
                        "timestamp_seconds": event.timestamp_seconds,
                        "confidence": event.confidence,
                    }
                    for event in analysis.events
                ],
            }
            if analysis
            else None
        ),
        "video_paths": [_store_path(video_path, base) for video_path in state.video_paths],
        "footage_strategy": state.footage_strategy,
        "playhead_seconds": state.playhead_seconds,
    }


def _state_from_dict(payload: dict[str, Any], base: Path) -> ProjectState:
    song_payload = payload.get("song")
    song = None
    if song_payload is not None:
        song = SongMetadata(
            path=_restore_path(song_payload["path"], base),
            duration_seconds=float(song_payload["duration_seconds"]),
            sample_rate=int(song_payload["sample_rate"]),
            channels=int(song_payload["channels"]),
            codec=str(song_payload["codec"]),
            waveform_peaks=tuple(float(value) for value in song_payload.get("waveform_peaks", [])),
        )
    analysis_payload = payload.get("analysis")
    analysis = None
    if analysis_payload is not None:
        if song is None:
            raise ValueError("analysis requires song metadata")
        analysis = MusicAnalysis(
            song=song,
            stems=tuple(
                StemArtifact(str(stem["name"]), _restore_path(stem["path"], base))
                for stem in analysis_payload.get("stems", [])
            ),
            events=tuple(
                MusicalEvent(
                    EventKind(event["kind"]),
                    float(event["timestamp_seconds"]),
                    float(event["confidence"]),
                )
                for event in analysis_payload.get("events", [])
            ),
            model_name=str(analysis_payload["model_name"]),
        )
    return ProjectState(
        song=song,
        analysis=analysis,
        video_paths=tuple(_restore_path(value, base) for value in payload.get("video_paths", [])),
        footage_strategy=str(payload.get("footage_strategy", "Movement based")),
        playhead_seconds=float(payload.get("playhead_seconds", 0.0)),
    )


def _store_path(path: Path, base: Path) -> str:
    path = path.resolve()
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return str(path)


def _restore_path(value: object, base: Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else (base / path).resolve()
