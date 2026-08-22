from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from kinebeat.domain import GeneratedTimeline, TimelineClip
from kinebeat.processing import render_video_preview


def _write_color_video(path: Path, color: tuple[int, int, int]) -> None:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 96
        stream.height = 54
        stream.pix_fmt = "yuv420p"
        for index in range(10):
            pixels = np.empty((54, 96, 3), dtype=np.uint8)
            pixels[:] = color
            frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, 10)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def test_preview_renderer_outputs_timeline_clip_order(tmp_path: Path) -> None:
    red = tmp_path / "red.mp4"
    blue = tmp_path / "blue.mp4"
    output = tmp_path / "preview.mp4"
    _write_color_video(red, (230, 20, 20))
    _write_color_video(blue, (20, 20, 230))
    timeline = GeneratedTimeline(
        (
            TimelineClip(red, 0.0, 1.0),
            TimelineClip(blue, 1.0, 2.0),
        ),
        seed=12,
    )
    progress: list[tuple[int, str]] = []

    result = render_video_preview(
        timeline,
        output,
        width=160,
        height=90,
        frames_per_second=10,
        progress=lambda value, detail: progress.append((value, detail)),
        cancelled=lambda: False,
    )

    with av.open(str(result)) as container:
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]

    assert len(frames) == 20
    assert float(frames[2][..., 0].mean()) > float(frames[2][..., 2].mean()) * 4
    assert float(frames[15][..., 2].mean()) > float(frames[15][..., 0].mean()) * 4
    assert progress[0] == (0, "Preparing video preview")
    assert progress[-1] == (100, "Video preview ready")


def test_preview_renderer_removes_partial_file_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "preview.mp4"
    _write_color_video(source, (80, 120, 160))
    timeline = GeneratedTimeline((TimelineClip(source, 0.0, 1.0),), seed=1)

    try:
        render_video_preview(
            timeline,
            output,
            progress=lambda *_: None,
            cancelled=lambda: True,
        )
    except RuntimeError as error:
        assert "cancelled" in str(error)
    else:
        raise AssertionError("Expected preview cancellation")

    assert not output.exists()
    assert not tuple(tmp_path.glob(".*.tmp.mp4"))
