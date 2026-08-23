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
from kinebeat.domain.output import OutputFormat, resolve_output_format
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
    "OutputFormat",
    "ProjectFormatError",
    "ProjectState",
    "SongMetadata",
    "StemArtifact",
    "TimelineClip",
    "load_project",
    "resolve_output_format",
    "save_project",
]
