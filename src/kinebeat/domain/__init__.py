"""Immutable domain models used by processing and UI layers."""

from kinebeat.domain.music import (
    DEFAULT_EFFECT_MAPPINGS,
    EffectAction,
    EventKind,
    InstrumentMapping,
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
from kinebeat.domain.timeline import GeneratedTimeline, TimelineClip

__all__ = [
    "DEFAULT_EFFECT_MAPPINGS",
    "EffectAction",
    "EventKind",
    "GeneratedTimeline",
    "InstrumentMapping",
    "MusicAnalysis",
    "MusicalEvent",
    "ProjectFormatError",
    "ProjectState",
    "SongMetadata",
    "StemArtifact",
    "TimelineClip",
    "load_project",
    "save_project",
]
