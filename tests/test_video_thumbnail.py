from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from kinebeat.processing import extract_video_thumbnail, inspect_video_media


def _write_sequence_video(path: Path) -> None:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 96
        stream.height = 54
        stream.pix_fmt = "yuv420p"
        for index in range(20):
            pixels = np.empty((54, 96, 3), dtype=np.uint8)
            pixels[:] = (220, 35, 20) if index < 10 else (20, 45, 220)
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def test_video_thumbnail_decodes_and_crops_a_representative_frame(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_sequence_video(source)

    thumbnail = extract_video_thumbnail(source, width=72, height=45)

    assert thumbnail.shape == (45, 72, 3)
    assert thumbnail.dtype == np.uint8
    assert thumbnail.flags.c_contiguous
    assert float(thumbnail[..., 0].mean()) > float(thumbnail[..., 2].mean()) * 4


def test_video_media_check_returns_usable_duration(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _write_sequence_video(source)

    result = inspect_video_media(source)

    assert result.duration_seconds == 2.0
    assert (result.source_width, result.source_height) == (96, 54)
    assert result.thumbnail.shape == (45, 72, 3)


def test_video_media_check_rejects_invalid_input(tmp_path: Path) -> None:
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"this is not video data")

    with pytest.raises(ValueError, match="could not decode video"):
        inspect_video_media(source)
