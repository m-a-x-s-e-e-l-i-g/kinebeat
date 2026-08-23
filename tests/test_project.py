import json
from pathlib import Path

import pytest

from kinebeat.domain import (
    DEFAULT_EFFECT_MAPPINGS,
    EffectAction,
    EventKind,
    GeneratedTimeline,
    InstrumentMapping,
    MusicalEvent,
    MusicAnalysis,
    ProjectFormatError,
    ProjectState,
    SongMetadata,
    StemArtifact,
    TimelineClip,
    load_project,
    save_project,
)


def test_project_round_trip_preserves_analysis_and_media_paths(tmp_path: Path) -> None:
    song_path = tmp_path / "media" / "song.wav"
    video_path = tmp_path / "media" / "clip.mp4"
    stem_path = tmp_path / "cache" / "drums.wav"
    song_path.parent.mkdir()
    stem_path.parent.mkdir()
    song_path.touch()
    video_path.touch()
    stem_path.touch()
    song = SongMetadata(song_path, 63.5, 48000, 2, "pcm_s16le", (0.1, 0.8, 0.3))
    analysis = MusicAnalysis(
        song,
        (StemArtifact("drums", stem_path),),
        (MusicalEvent(EventKind.KICK, 1.25, 0.91),),
        "htdemucs_6s",
    )
    mappings = (
        InstrumentMapping(EventKind.KICK, EffectAction.RANDOM_EFFECT),
        InstrumentMapping(EventKind.BASS, EffectAction.ADD_INTENSITY),
        InstrumentMapping(EventKind.SNARE, EffectAction.VHS),
        InstrumentMapping(EventKind.VOCAL, EffectAction.VIDEO_VOLUME),
    )
    generated_timeline = GeneratedTimeline(
        (TimelineClip(video_path, 0.0, 1.25), TimelineClip(video_path, 1.25, 63.5, locked=True)),
        seed=782,
    )
    state = ProjectState(
        song,
        analysis,
        (video_path,),
        "Random",
        12.75,
        mappings,
        generated_timeline,
    )
    project_path = tmp_path / "edit.kinebeat"

    save_project(project_path, state)
    restored = load_project(project_path)

    assert restored == state
    assert '"path": "media/song.wav"' in project_path.read_text(encoding="utf-8")
    assert restored.effect_mappings == mappings
    assert restored.generated_timeline == generated_timeline


def test_project_loader_rejects_unrelated_json(tmp_path: Path) -> None:
    path = tmp_path / "not-a-project.kinebeat"
    path.write_text('{"format": "something-else", "version": 1}', encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="not a Kinebeat"):
        load_project(path)


def test_older_project_without_mappings_receives_new_defaults(tmp_path: Path) -> None:
    path = tmp_path / "older.kinebeat"
    save_project(path, ProjectState())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("effect_mappings")
    path.write_text(json.dumps(payload), encoding="utf-8")

    restored = load_project(path)

    assert restored.effect_mappings == DEFAULT_EFFECT_MAPPINGS
