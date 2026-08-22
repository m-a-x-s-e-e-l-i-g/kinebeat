from pathlib import Path

import pytest

from kinebeat.domain import EventKind, MusicalEvent, SongMetadata


def test_song_metadata_formats_duration() -> None:
    song = SongMetadata(Path("song.wav"), 185.2, 48000, 2, "pcm_s24le")

    assert song.display_duration == "3:05"


def test_musical_event_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        MusicalEvent(EventKind.KICK, 1.2, 1.1)
