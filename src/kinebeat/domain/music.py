from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class EventKind(StrEnum):
    KICK = "kick"
    SNARE = "snare"
    HI_HAT = "hi_hat"
    BASS = "bass"
    VOCAL = "vocal"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SongMetadata:
    path: Path
    duration_seconds: float
    sample_rate: int
    channels: int
    codec: str
    waveform_peaks: tuple[float, ...] = ()

    @property
    def display_duration(self) -> str:
        total_seconds = max(0, round(self.duration_seconds))
        minutes, seconds = divmod(total_seconds, 60)
        return f"{minutes}:{seconds:02d}"


@dataclass(frozen=True, slots=True)
class StemArtifact:
    name: str
    path: Path


@dataclass(frozen=True, slots=True)
class MusicalEvent:
    kind: EventKind
    timestamp_seconds: float
    confidence: float

    def __post_init__(self) -> None:
        if self.timestamp_seconds < 0:
            raise ValueError("timestamp_seconds must be non-negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class MusicAnalysis:
    song: SongMetadata
    stems: tuple[StemArtifact, ...]
    events: tuple[MusicalEvent, ...]
    model_name: str

    def events_for(self, kind: EventKind) -> tuple[MusicalEvent, ...]:
        return tuple(event for event in self.events if event.kind is kind)
