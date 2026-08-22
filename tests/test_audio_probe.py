from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from kinebeat.processing.audio_probe import probe_song


def _write_sine_wave(path: Path, duration: float = 0.25, sample_rate: int = 16000) -> None:
    frame_count = round(duration * sample_rate)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        samples = (
            struct.pack("<h", round(math.sin(2 * math.pi * 440 * index / sample_rate) * 16000))
            for index in range(frame_count)
        )
        output.writeframes(b"".join(samples))


def test_probe_song_reads_metadata_and_builds_normalized_waveform(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    _write_sine_wave(source)

    result = probe_song(source, peak_count=32)

    assert result.path == source.resolve()
    assert result.sample_rate == 16000
    assert result.channels == 1
    assert result.duration_seconds == 0.25
    assert len(result.waveform_peaks) == 32
    assert max(result.waveform_peaks) == 1.0
