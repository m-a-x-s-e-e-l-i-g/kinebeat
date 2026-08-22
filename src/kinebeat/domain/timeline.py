from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TimelineClip:
    source_path: Path
    timeline_start_seconds: float
    timeline_end_seconds: float
    source_start_seconds: float = 0.0
    locked: bool = False

    def __post_init__(self) -> None:
        if self.timeline_start_seconds < 0:
            raise ValueError("timeline_start_seconds must be non-negative")
        if self.timeline_end_seconds <= self.timeline_start_seconds:
            raise ValueError("timeline_end_seconds must be after timeline_start_seconds")
        if self.source_start_seconds < 0:
            raise ValueError("source_start_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class GeneratedTimeline:
    clips: tuple[TimelineClip, ...]
    seed: int

    def __post_init__(self) -> None:
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
