from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import av
import numpy as np

from kinebeat.domain import SongMetadata

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class AudioProbeCancelled(RuntimeError):
    pass


def probe_song(
    path: Path,
    *,
    peak_count: int = 720,
    progress: ProgressCallback | None = None,
    cancelled: CancelCheck | None = None,
) -> SongMetadata:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Music file not found: {source}")
    if progress:
        progress(5, "Reading song information")

    with av.open(str(source)) as container:
        if not container.streams.audio:
            raise ValueError("The selected file does not contain an audio stream.")
        stream = container.streams.audio[0]
        duration = _duration_seconds(container, stream)
        sample_rate = int(stream.codec_context.sample_rate or stream.rate or 0)
        channels = int(stream.codec_context.channels or 0)
        codec = stream.codec_context.name or "unknown"
        samples: list[np.ndarray] = []
        decoded_seconds = 0.0

        for frame in container.decode(stream):
            if cancelled and cancelled():
                raise AudioProbeCancelled("Song import cancelled.")
            array = frame.to_ndarray()
            mono = _mono_samples(array)
            if mono.size:
                samples.append(mono)
            decoded_seconds += float(frame.samples) / float(frame.sample_rate or sample_rate or 1)
            if progress and duration > 0:
                ratio = min(1.0, decoded_seconds / duration)
                progress(10 + round(ratio * 80), "Building waveform")

    waveform = np.concatenate(samples) if samples else np.zeros(1, dtype=np.float32)
    peaks = _waveform_peaks(waveform, peak_count)
    if progress:
        progress(100, "Song ready")
    return SongMetadata(
        path=source,
        duration_seconds=duration or decoded_seconds,
        sample_rate=sample_rate,
        channels=channels,
        codec=codec,
        waveform_peaks=peaks,
    )


def _duration_seconds(
    container: av.container.InputContainer, stream: av.audio.stream.AudioStream
) -> float:
    if stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        return float(container.duration / av.time_base)
    return 0.0


def _mono_samples(array: np.ndarray) -> np.ndarray:
    values = np.asarray(array, dtype=np.float32)
    if values.ndim == 1:
        return values
    if values.ndim != 2:
        return values.reshape(-1)
    channel_axis = 0 if values.shape[0] <= values.shape[1] else 1
    return values.mean(axis=channel_axis)


def _waveform_peaks(samples: np.ndarray, peak_count: int) -> tuple[float, ...]:
    peak_count = max(1, peak_count)
    if samples.size == 0:
        return (0.0,) * peak_count
    boundaries = np.linspace(0, samples.size, peak_count + 1, dtype=np.int64)
    peaks = np.zeros(peak_count, dtype=np.float32)
    for index in range(peak_count):
        start, end = int(boundaries[index]), int(boundaries[index + 1])
        if end > start:
            peaks[index] = float(np.max(np.abs(samples[start:end])))
    maximum = float(np.max(peaks))
    if maximum > 0:
        peaks /= maximum
    return tuple(float(value) for value in peaks)
