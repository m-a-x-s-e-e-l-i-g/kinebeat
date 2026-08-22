from pathlib import Path

from kinebeat.domain import EventKind, MusicalEvent, MusicAnalysis, SongMetadata
from kinebeat.processing import generate_first_cut


def _analysis() -> MusicAnalysis:
    song = SongMetadata(Path("song.wav"), 10.0, 48000, 2, "pcm_s16le")
    return MusicAnalysis(
        song,
        (),
        (
            MusicalEvent(EventKind.KICK, 2.0, 0.9),
            MusicalEvent(EventKind.SNARE, 3.0, 0.8),
            MusicalEvent(EventKind.KICK, 6.5, 0.95),
        ),
        "test",
    )


def test_first_cut_places_clip_boundaries_on_kicks() -> None:
    progress: list[tuple[int, str]] = []

    result = generate_first_cut(
        _analysis(),
        (Path("one.mp4"), Path("two.mp4")),
        strategy="Import order",
        seed=42,
        progress=lambda value, detail: progress.append((value, detail)),
        cancelled=lambda: False,
    )

    assert [(clip.timeline_start_seconds, clip.timeline_end_seconds) for clip in result.clips] == [
        (0.0, 2.0),
        (2.0, 6.5),
        (6.5, 10.0),
    ]
    assert [clip.source_path for clip in result.clips] == [
        Path("one.mp4"),
        Path("two.mp4"),
        Path("one.mp4"),
    ]
    assert progress[0] == (5, "Finding kick cut points")
    assert progress[-1] == (100, "First cut ready · 3 edits")


def test_random_first_cut_is_reproducible_from_seed() -> None:
    kwargs = {
        "strategy": "Random",
        "seed": 173,
        "progress": lambda *_: None,
        "cancelled": lambda: False,
    }
    paths = (Path("one.mp4"), Path("two.mp4"), Path("three.mp4"))

    first = generate_first_cut(_analysis(), paths, **kwargs)
    second = generate_first_cut(_analysis(), paths, **kwargs)

    assert first == second
