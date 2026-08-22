"""Immutable domain models used by processing and UI layers."""

from kinebeat.domain.music import (
    EventKind,
    MusicalEvent,
    MusicAnalysis,
    SongMetadata,
    StemArtifact,
)
from kinebeat.domain.project import (
    ProjectFormatError,
    ProjectState,
    load_project,
    save_project,
)

__all__ = [
    "EventKind",
    "MusicAnalysis",
    "MusicalEvent",
    "ProjectFormatError",
    "ProjectState",
    "SongMetadata",
    "StemArtifact",
    "load_project",
    "save_project",
]
