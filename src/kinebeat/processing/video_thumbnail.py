from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import av
import numpy as np

from kinebeat.processing.preview_renderer import (
    _decode_video_frames,
    _unreadable_video_message,
)


@dataclass(frozen=True, slots=True)
class VideoMediaCheck:
    thumbnail: np.ndarray
    duration_seconds: float
    source_width: int = 1920
    source_height: int = 1080


def inspect_video_media(
    path: Path,
    *,
    width: int = 72,
    height: int = 45,
) -> VideoMediaCheck:
    """Validate a source clip and return its duration and representative frame."""
    if width <= 0 or height <= 0:
        raise ValueError("Thumbnail dimensions must be positive.")

    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video clip is missing: {source}")

    try:
        with av.open(str(source)) as container:
            if not container.streams.video:
                raise ValueError(f"Video clip does not contain video: {source.name}")
            container.flags |= av.container.Flags.discard_corrupt.value
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            duration = _video_duration(container, stream)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError(f"Video clip has no usable duration: {source.name}")
            target_seconds = min(2.0, duration * 0.08)
            if stream.time_base:
                container.seek(
                    round(target_seconds / float(stream.time_base)),
                    stream=stream,
                    backward=True,
                )
            selected: av.VideoFrame | None = None
            for frame in _decode_video_frames(container, stream):
                selected = frame
                if frame.time is None or float(frame.time) + 1e-6 >= target_seconds:
                    break
            if selected is None:
                raise ValueError(_unreadable_video_message(source))
            return VideoMediaCheck(
                _cover_frame(selected, width, height),
                duration,
                selected.width,
                selected.height,
            )
    except av.error.FFmpegError as error:
        raise ValueError(_unreadable_video_message(source, error)) from error


def extract_video_thumbnail(
    path: Path,
    *,
    width: int = 72,
    height: int = 45,
) -> np.ndarray:
    """Decode a representative source frame into a cropped RGB thumbnail."""
    return inspect_video_media(path, width=width, height=height).thumbnail


def _video_duration(
    container: av.container.InputContainer,
    stream: av.video.stream.VideoStream,
) -> float:
    if stream.duration is not None and stream.time_base is not None:
        return float(stream.duration * stream.time_base)
    if container.duration is not None:
        return float(container.duration) / 1_000_000
    return 0.0


def _cover_frame(frame: av.VideoFrame, width: int, height: int) -> np.ndarray:
    scale = max(width / frame.width, height / frame.height)
    scaled_width = max(width, math.ceil(frame.width * scale))
    scaled_height = max(height, math.ceil(frame.height * scale))
    image = frame.reformat(
        width=scaled_width,
        height=scaled_height,
        format="rgb24",
    ).to_ndarray()
    left = max(0, (scaled_width - width) // 2)
    top = max(0, (scaled_height - height) // 2)
    return np.ascontiguousarray(image[top : top + height, left : left + width])
