from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest

from kinebeat.domain import (
    EffectAction,
    EventKind,
    GeneratedTimeline,
    InstrumentMapping,
    MusicalEvent,
    MusicAnalysis,
    SongMetadata,
    TimelineClip,
)
from kinebeat.processing import generate_video_edit_preview, render_video_preview
from kinebeat.processing.preview_renderer import _decode_video_frames


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


def _write_sequence_video(path: Path, colors: tuple[tuple[int, int, int], ...]) -> None:
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("mpeg4", rate=10)
        stream.width = 96
        stream.height = 54
        stream.pix_fmt = "yuv420p"
        frame_index = 0
        for color in colors:
            for _ in range(10):
                pixels = np.empty((54, 96, 3), dtype=np.uint8)
                pixels[:] = color
                frame = av.VideoFrame.from_ndarray(pixels, format="rgb24")
                frame.pts = frame_index
                frame.time_base = Fraction(1, 10)
                frame_index += 1
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
    assert progress[0] == (0, "Preparing video preview · 0 effect hits")
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


def test_video_edit_preview_renders_mapped_effect_hits(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "effected.mp4"
    _write_color_video(source, (210, 40, 25))
    song = SongMetadata(tmp_path / "song.wav", 1.0, 48000, 2, "pcm_s16le")
    analysis = MusicAnalysis(
        song,
        (),
        (MusicalEvent(EventKind.SNARE, 0.2, 1.0),),
        "test",
    )

    result = generate_video_edit_preview(
        analysis,
        (source,),
        strategy="Import order",
        seed=81,
        output_path=output,
        effect_mappings=(InstrumentMapping(EventKind.SNARE, EffectAction.VHS),),
        progress=lambda *_: None,
        cancelled=lambda: False,
        width=160,
        height=90,
        frames_per_second=10,
    )

    with av.open(str(result.path)) as container:
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]

    assert result.effect_count == 1
    assert float(frames[5].std(axis=(0, 1)).mean()) > 2.0


def test_generated_preview_advances_through_unused_source_ranges(tmp_path: Path) -> None:
    source = tmp_path / "sequence.mp4"
    output = tmp_path / "non-repeating.mp4"
    _write_sequence_video(
        source,
        (
            (230, 20, 20),
            (20, 230, 20),
            (20, 20, 230),
        ),
    )
    song = SongMetadata(tmp_path / "song.wav", 3.0, 48000, 2, "pcm_s16le")
    analysis = MusicAnalysis(
        song,
        (),
        (
            MusicalEvent(EventKind.KICK, 1.0, 1.0),
            MusicalEvent(EventKind.KICK, 2.0, 1.0),
        ),
        "test",
    )

    result = generate_video_edit_preview(
        analysis,
        (source,),
        strategy="Import order",
        seed=8,
        output_path=output,
        effect_mappings=(),
        progress=lambda *_: None,
        cancelled=lambda: False,
        width=160,
        height=90,
        frames_per_second=10,
    )

    with av.open(str(result.path)) as container:
        frames = [frame.to_ndarray(format="rgb24") for frame in container.decode(video=0)]

    assert [clip.source_start_seconds for clip in result.timeline.clips] == [0.0, 1.0, 2.0]
    assert float(frames[2][..., 0].mean()) > float(frames[2][..., 1].mean()) * 4
    assert float(frames[12][..., 1].mean()) > float(frames[12][..., 0].mean()) * 4
    assert float(frames[22][..., 2].mean()) > float(frames[22][..., 0].mean()) * 4


def test_video_packet_decoder_skips_isolated_invalid_data() -> None:
    class FakePacket:
        def __init__(self, frames=None, error=None):
            self.frames = frames or []
            self.error = error

        def decode(self):
            if self.error:
                raise self.error
            return self.frames

    class FakeContainer:
        def demux(self, _stream):
            return iter(
                (
                    FakePacket(error=av.InvalidDataError(1094995529, "Invalid data")),
                    FakePacket(frames=["recovered-frame"]),
                )
            )

    assert list(_decode_video_frames(FakeContainer(), object())) == ["recovered-frame"]


def test_video_edit_preview_names_an_unreadable_library_clip(tmp_path: Path) -> None:
    source = tmp_path / "broken-camera-clip.mp4"
    source.write_bytes(b"this is not video data")
    output = tmp_path / "preview.mp4"
    song = SongMetadata(tmp_path / "song.wav", 1.0, 48000, 2, "pcm_s16le")
    analysis = MusicAnalysis(song, (), (), "test")

    with pytest.raises(ValueError) as raised:
        generate_video_edit_preview(
            analysis,
            (source,),
            strategy="Import order",
            seed=9,
            output_path=output,
            effect_mappings=(),
            progress=lambda *_: None,
            cancelled=lambda: False,
            width=160,
            height=90,
            frames_per_second=10,
        )

    message = str(raised.value)
    assert "broken-camera-clip.mp4" in message
    assert "Remove it from the Media library" in message
    assert "avcodec_send_packet" not in message
