from __future__ import annotations

from collections.abc import Callable

import numpy as np

from kinebeat.domain import EventKind, MusicalEvent, StemArtifact

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


def detect_musical_events(
    stems: tuple[StemArtifact, ...],
    *,
    progress: ProgressCallback,
    cancelled: CancelCheck,
) -> tuple[MusicalEvent, ...]:
    try:
        import librosa
    except ImportError as error:
        raise RuntimeError(
            "Musical event detection is not installed. Install Kinebeat with the analysis extra."
        ) from error

    stem_paths = {stem.name: stem.path for stem in stems}
    events: list[MusicalEvent] = []
    ordered = ("drums", "bass", "vocals", "other")
    for index, stem_name in enumerate(ordered):
        if cancelled():
            raise RuntimeError("Music analysis cancelled.")
        path = stem_paths.get(stem_name)
        if path is None:
            continue
        progress(74 + index * 6, f"Finding {stem_name} events")
        signal, sample_rate = librosa.load(path, sr=22050, mono=True)
        onset_envelope = librosa.onset.onset_strength(y=signal, sr=sample_rate)
        onset_frames = librosa.onset.onset_detect(
            onset_envelope=onset_envelope,
            sr=sample_rate,
            backtrack=True,
            units="frames",
        )
        times = librosa.frames_to_time(onset_frames, sr=sample_rate)
        strengths = _normalized_strengths(onset_envelope, onset_frames)
        if stem_name == "drums":
            kinds = _classify_drum_events(signal, sample_rate, onset_frames)
        else:
            kind = {
                "bass": EventKind.BASS,
                "vocals": EventKind.VOCAL,
                "other": EventKind.OTHER,
            }[stem_name]
            kinds = (kind,) * len(onset_frames)
        events.extend(
            MusicalEvent(kind=kind, timestamp_seconds=float(time), confidence=float(strength))
            for kind, time, strength in zip(kinds, times, strengths, strict=True)
        )
    progress(100, "Timeline events ready")
    return tuple(sorted(events, key=lambda event: (event.timestamp_seconds, event.kind.value)))


def _normalized_strengths(envelope: np.ndarray, frames: np.ndarray) -> tuple[float, ...]:
    if len(frames) == 0:
        return ()
    selected = np.asarray(envelope)[frames]
    maximum = float(np.max(selected)) if selected.size else 0.0
    if maximum <= 0:
        return (0.5,) * len(frames)
    return tuple(float(max(0.05, min(1.0, value / maximum))) for value in selected)


def _classify_drum_events(
    signal: np.ndarray, sample_rate: int, onset_frames: np.ndarray
) -> tuple[EventKind, ...]:
    import librosa

    if len(onset_frames) == 0:
        return ()
    spectrum = np.abs(librosa.stft(signal, n_fft=2048, hop_length=512))
    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    classes: list[EventKind] = []
    for frame in onset_frames:
        column = spectrum[:, min(int(frame), spectrum.shape[1] - 1)]
        energy = float(np.sum(column))
        centroid = float(np.sum(frequencies * column) / energy) if energy > 0 else 0.0
        low_ratio = float(np.sum(column[frequencies < 180]) / energy) if energy > 0 else 0.0
        if low_ratio >= 0.42 or centroid < 1100:
            classes.append(EventKind.KICK)
        elif centroid < 5200:
            classes.append(EventKind.SNARE)
        else:
            classes.append(EventKind.HI_HAT)
    return tuple(classes)
