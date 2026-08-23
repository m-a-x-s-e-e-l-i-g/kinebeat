from __future__ import annotations

import numpy as np
import pytest

from kinebeat.domain import (
    EffectAction,
    EventKind,
    InstrumentMapping,
    MusicalEvent,
    MusicAnalysis,
    SongMetadata,
)
from kinebeat.processing import EffectCue, VideoEffectProcessor, build_effect_cues


def _moving_frame(index: int) -> np.ndarray:
    height, width = 64, 96
    y, x = np.indices((height, width))
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[..., 0] = (x * 2 + index * 7) % 256
    frame[..., 1] = (y * 3 + index * 5) % 256
    frame[..., 2] = (x + y + index * 11) % 256
    left = 28 + index % 8
    frame[15:54, left : left + 30] = (235, 72, 28)
    return frame


@pytest.mark.parametrize(
    "action",
    [
        EffectAction.GLITCH,
        EffectAction.VHS,
        EffectAction.SILHOUETTE_STRETCH,
        EffectAction.VIDEO_VOLUME,
        EffectAction.DATAMOSH,
        EffectAction.TIME_BEND,
        EffectAction.ADD_INTENSITY,
        EffectAction.ADD_AMBIANCE,
        EffectAction.LIGHT_EFFECT,
    ],
)
def test_every_rendered_effect_changes_video_pixels(action: EffectAction) -> None:
    cue = EffectCue(action, EventKind.SNARE, 1.0, 2.0, 1.0, 42)
    processor = VideoEffectProcessor((cue,), frames_per_second=10)
    for index in range(10):
        processor.process(_moving_frame(index), index / 10)
    source = _moving_frame(12)

    effected = processor.process(source, 1.25)

    assert effected.shape == source.shape
    assert effected.dtype == np.uint8
    assert float(np.mean(np.abs(effected.astype(np.int16) - source.astype(np.int16)))) > 0.5


def test_effect_processing_is_reproducible_from_cue_seed() -> None:
    cue = EffectCue(EffectAction.GLITCH, EventKind.SNARE, 0.0, 1.0, 1.0, 991)
    first = VideoEffectProcessor((cue,), frames_per_second=24)
    second = VideoEffectProcessor((cue,), frames_per_second=24)
    frames = [_moving_frame(index) for index in range(6)]

    first_results = [first.process(frame, index / 24) for index, frame in enumerate(frames)]
    second_results = [second.process(frame, index / 24) for index, frame in enumerate(frames)]

    for left, right in zip(first_results, second_results, strict=True):
        np.testing.assert_array_equal(left, right)


def test_random_mapping_builds_concrete_effect_cues_deterministically(tmp_path) -> None:
    song = SongMetadata(tmp_path / "song.wav", 4.0, 48000, 2, "pcm_s16le")
    analysis = MusicAnalysis(
        song,
        (),
        (
            MusicalEvent(EventKind.KICK, 0.5, 0.9),
            MusicalEvent(EventKind.SNARE, 1.0, 0.8),
            MusicalEvent(EventKind.SNARE, 2.0, 0.7),
        ),
        "test",
    )
    mappings = (
        InstrumentMapping(EventKind.KICK, EffectAction.CUT),
        InstrumentMapping(EventKind.SNARE, EffectAction.RANDOM_EFFECT),
    )

    first = build_effect_cues(analysis, mappings, seed=75)
    second = build_effect_cues(analysis, mappings, seed=75)

    assert first == second
    assert len(first) == 2
    assert all(cue.action is not EffectAction.RANDOM_EFFECT for cue in first)
    assert all(cue.instrument is EventKind.SNARE for cue in first)
