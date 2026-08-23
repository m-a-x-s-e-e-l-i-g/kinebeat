from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from kinebeat.processing import extract_video_thumbnail


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
