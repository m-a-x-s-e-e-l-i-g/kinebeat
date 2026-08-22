from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from kinebeat.domain import MusicalEvent, MusicAnalysis, SongMetadata, StemArtifact
from kinebeat.processing.demucs_backend import DemucsSeparator
from kinebeat.processing.event_detection import detect_musical_events

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]
EventDetector = Callable[..., tuple[MusicalEvent, ...]]


class Separator(Protocol):
    model_name: str

    def separate(
        self,
        source: Path,
        output_root: Path,
        *,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> tuple[StemArtifact, ...]: ...


class MusicAnalysisService:
    def __init__(
        self,
        *,
        cache_root: Path,
        separator: Separator | None = None,
        event_detector: EventDetector = detect_musical_events,
    ) -> None:
        self.cache_root = cache_root
        self.separator = separator or DemucsSeparator()
        self.event_detector = event_detector

    def analyse(
        self,
        song: SongMetadata,
        *,
        progress: ProgressCallback,
        cancelled: CancelCheck,
    ) -> MusicAnalysis:
        analysis_root = self.cache_root / _source_key(song.path)
        stems = self.separator.separate(
            song.path,
            analysis_root,
            progress=progress,
            cancelled=cancelled,
        )
        events = self.event_detector(stems, progress=progress, cancelled=cancelled)
        return MusicAnalysis(
            song=song,
            stems=stems,
            events=events,
            model_name=self.separator.model_name,
        )


def _source_key(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()[:20]
