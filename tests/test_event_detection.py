import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from kinebeat.domain import EventKind, StemArtifact
from kinebeat.processing import event_detection


def test_detection_classifies_peak_frames_but_keeps_backtracked_timing(monkeypatch) -> None:
    envelope = np.zeros(32, dtype=np.float32)
    envelope[8] = 0.5
    envelope[20] = 1.0
    captured_frames: list[int] = []
    fake_librosa = SimpleNamespace(
        load=lambda *_args, **_kwargs: (np.zeros(2048), 22050),
        onset=SimpleNamespace(
            onset_strength=lambda **_kwargs: envelope,
            onset_detect=lambda **_kwargs: np.array([8, 20]),
            onset_backtrack=lambda frames, _envelope: np.asarray(frames) - 3,
        ),
        frames_to_time=lambda frames, **_kwargs: np.asarray(frames, dtype=float) / 10,
    )
    monkeypatch.setitem(sys.modules, "librosa", fake_librosa)

    def classify(_signal, _sample_rate, frames):
        captured_frames.extend(int(frame) for frame in frames)
        return (EventKind.KICK, EventKind.SNARE)

    monkeypatch.setattr(event_detection, "_classify_drum_events", classify)

    events = event_detection.detect_musical_events(
        (StemArtifact("drums", Path("drums.wav")),),
        progress=lambda *_: None,
        cancelled=lambda: False,
    )

    assert captured_frames == [8, 20]
    assert [event.timestamp_seconds for event in events] == [0.5, 1.7]
    assert [event.confidence for event in events] == [0.5, 1.0]


def test_drum_classifier_recognizes_broadband_kick_with_strong_low_end(monkeypatch) -> None:
    frequencies = np.array([100.0, 1000.0, 3000.0, 6000.0])
    spectrum = np.array(
        [
            [0.16, 0.03, 0.01],
            [0.14, 0.57, 0.04],
            [0.20, 0.30, 0.15],
            [0.50, 0.10, 0.80],
        ]
    )
    fake_librosa = SimpleNamespace(
        stft=lambda *_args, **_kwargs: spectrum,
        fft_frequencies=lambda **_kwargs: frequencies,
    )
    monkeypatch.setitem(sys.modules, "librosa", fake_librosa)

    kinds = event_detection._classify_drum_events(
        np.zeros(2048),
        22050,
        np.array([0, 1, 2]),
    )

    assert kinds == (EventKind.KICK, EventKind.SNARE, EventKind.HI_HAT)
