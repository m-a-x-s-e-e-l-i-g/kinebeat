from __future__ import annotations

from pathlib import Path

from kinebeat.domain import EventKind, MusicalEvent, SongMetadata, StemArtifact
from kinebeat.processing.analyser import MusicAnalysisService


class FakeSeparator:
    model_name = "fake_6s"

    def separate(self, source: Path, output_root: Path, *, progress, cancelled):
        assert source.is_file()
        assert not cancelled()
        progress(70, "Separated")
        return (StemArtifact("drums", output_root / "drums.wav"),)


def fake_detector(stems, *, progress, cancelled):
    assert stems[0].name == "drums"
    assert not cancelled()
    progress(100, "Detected")
    return (MusicalEvent(EventKind.KICK, 0.5, 0.9),)


def test_analysis_service_keeps_processing_outside_qt(tmp_path: Path) -> None:
    source = tmp_path / "song.wav"
    source.write_bytes(b"song fixture")
    song = SongMetadata(source, 2.0, 44100, 2, "pcm_s16le")
    progress: list[tuple[int, str]] = []
    service = MusicAnalysisService(
        cache_root=tmp_path / "cache",
        separator=FakeSeparator(),
        event_detector=fake_detector,
    )

    result = service.analyse(
        song,
        progress=lambda value, detail: progress.append((value, detail)),
        cancelled=lambda: False,
    )

    assert result.model_name == "fake_6s"
    assert result.events[0].kind is EventKind.KICK
    assert progress == [(70, "Separated"), (100, "Detected")]
