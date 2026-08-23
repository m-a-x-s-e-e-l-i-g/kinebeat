from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av
import numpy as np

from kinebeat.domain import (
    DEFAULT_EFFECT_MAPPINGS,
    GeneratedTimeline,
    InstrumentMapping,
    MusicAnalysis,
)
from kinebeat.processing.timeline_generator import generate_first_cut
from kinebeat.processing.video_effects import EffectCue, VideoEffectProcessor, build_effect_cues

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


class PreviewRenderCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VideoEditPreview:
    timeline: GeneratedTimeline
    path: Path
    width: int
    height: int
    frames_per_second: int
    effect_count: int = 0


def generate_video_edit_preview(
    analysis: MusicAnalysis,
    video_paths: tuple[Path, ...],
    *,
    strategy: str,
    seed: int,
    output_path: Path,
    progress: ProgressCallback,
    cancelled: CancelCheck,
    effect_mappings: tuple[InstrumentMapping, ...] = DEFAULT_EFFECT_MAPPINGS,
    width: int = 640,
    height: int = 360,
    frames_per_second: int = 24,
) -> VideoEditPreview:
    source_durations = _probe_video_durations(
        video_paths,
        progress=lambda value, detail: progress(round(value * 0.08), detail),
        cancelled=cancelled,
    )
    timeline = generate_first_cut(
        analysis,
        video_paths,
        strategy=strategy,
        seed=seed,
        progress=lambda value, detail: progress(8 + round(value * 0.04), detail),
        cancelled=cancelled,
        source_durations=source_durations,
    )
    effect_cues = build_effect_cues(analysis, effect_mappings, seed=seed)
    preview_path = render_video_preview(
        timeline,
        output_path,
        progress=lambda value, detail: progress(12 + round(value * 0.88), detail),
        cancelled=cancelled,
        width=width,
        height=height,
        frames_per_second=frames_per_second,
        effect_cues=effect_cues,
    )
    return VideoEditPreview(
        timeline,
        preview_path,
        width,
        height,
        frames_per_second,
        len(effect_cues),
    )


def _probe_video_durations(
    video_paths: tuple[Path, ...],
    *,
    progress: ProgressCallback,
    cancelled: CancelCheck,
) -> dict[Path, float]:
    if not video_paths:
        raise ValueError("Import at least one video clip before generating a video edit.")

    durations: dict[Path, float] = {}
    progress(0, "Checking available unused footage")
    for index, path in enumerate(video_paths):
        if cancelled():
            raise PreviewRenderCancelled("Video preview generation was cancelled.")
        source = path.expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Video clip is missing: {source}")
        try:
            with av.open(str(source)) as container:
                if not container.streams.video:
                    raise ValueError(f"Video clip does not contain video: {source.name}")
                stream = container.streams.video[0]
                if stream.duration is not None and stream.time_base is not None:
                    duration = float(stream.duration * stream.time_base)
                elif container.duration is not None:
                    duration = float(container.duration) / 1_000_000
                else:
                    raise ValueError(
                        f"Kinebeat could not determine the duration of {source.name}."
                    )
        except av.error.FFmpegError as error:
            raise ValueError(f"Kinebeat could not read {source.name}: {error}") from error
        if duration <= 0:
            raise ValueError(f"Video clip has no usable duration: {source.name}")
        durations[path] = duration
        progress(
            round((index + 1) * 100 / len(video_paths)),
            f"Checked footage {index + 1} of {len(video_paths)}",
        )
    return durations


def render_video_preview(
    timeline: GeneratedTimeline,
    output_path: Path,
    *,
    progress: ProgressCallback,
    cancelled: CancelCheck,
    width: int = 640,
    height: int = 360,
    frames_per_second: int = 24,
    effect_cues: tuple[EffectCue, ...] = (),
) -> Path:
    if not timeline.clips:
        raise ValueError("The generated edit does not contain any clips.")
    if width <= 0 or height <= 0 or frames_per_second <= 0:
        raise ValueError("Preview dimensions and frame rate must be positive.")

    destination = output_path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}.{uuid.uuid4().hex}.tmp.mp4")
    total_frames = max(
        1,
        round(timeline.clips[-1].timeline_end_seconds * frames_per_second),
    )
    written_frames = 0
    last_progress = -1
    effect_processor = VideoEffectProcessor(
        effect_cues,
        frames_per_second=frames_per_second,
    )
    progress(0, f"Preparing video preview · {len(effect_cues)} effect hits")

    try:
        with av.open(str(temporary), mode="w") as output:
            stream = _add_preview_stream(output, width, height, frames_per_second)
            for clip_index, clip in enumerate(timeline.clips):
                if cancelled():
                    raise PreviewRenderCancelled("Video preview generation was cancelled.")
                start_frame = round(clip.timeline_start_seconds * frames_per_second)
                end_frame = round(clip.timeline_end_seconds * frames_per_second)
                frame_count = max(1, end_frame - start_frame)
                source_frames = _read_source_segment(
                    clip.source_path,
                    clip.source_start_seconds,
                    frame_count,
                    frames_per_second,
                    width,
                    height,
                    cancelled,
                )
                for rgb_frame in source_frames:
                    if cancelled():
                        raise PreviewRenderCancelled("Video preview generation was cancelled.")
                    effected_frame = effect_processor.process(
                        rgb_frame,
                        written_frames / frames_per_second,
                    )
                    frame = av.VideoFrame.from_ndarray(effected_frame, format="rgb24")
                    frame.pts = written_frames
                    frame.time_base = Fraction(1, frames_per_second)
                    for packet in stream.encode(frame):
                        output.mux(packet)
                    written_frames += 1
                    percentage = min(99, round(written_frames * 100 / total_frames))
                    if percentage != last_progress:
                        elapsed = written_frames / frames_per_second
                        duration = total_frames / frames_per_second
                        progress(
                            percentage,
                            f"Rendering preview · {_clock(elapsed)} / {_clock(duration)}",
                        )
                        last_progress = percentage
                progress(
                    min(99, round(written_frames * 100 / total_frames)),
                    f"Rendered edit {clip_index + 1} of {len(timeline.clips)}",
                )
            for packet in stream.encode():
                output.mux(packet)
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise

    progress(100, "Video preview ready")
    return destination


def _add_preview_stream(
    output: av.container.OutputContainer,
    width: int,
    height: int,
    frames_per_second: int,
) -> av.video.stream.VideoStream:
    try:
        stream = output.add_stream("libx264", rate=frames_per_second)
        stream.options = {"preset": "ultrafast", "crf": "30"}
    except av.error.FFmpegError:
        stream = output.add_stream("mpeg4", rate=frames_per_second)
        stream.bit_rate = 1_500_000
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    stream.time_base = Fraction(1, frames_per_second)
    return stream


def _read_source_segment(
    path: Path,
    source_start_seconds: float,
    frame_count: int,
    frames_per_second: int,
    width: int,
    height: int,
    cancelled: CancelCheck,
) -> Iterator[np.ndarray]:
    source = path.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Video clip is missing: {source}")
    with av.open(str(source)) as container:
        if not container.streams.video:
            raise ValueError(f"Video clip does not contain video: {source.name}")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if source_start_seconds > 0 and stream.time_base:
            seek_offset = round(source_start_seconds / float(stream.time_base))
            container.seek(seek_offset, stream=stream, backward=True)
        fallback_rate = float(stream.average_rate or frames_per_second)
        decoded_index = 0
        target_index = 0
        last_image: np.ndarray | None = None
        for frame in container.decode(stream):
            if cancelled():
                raise PreviewRenderCancelled("Video preview generation was cancelled.")
            frame_time = (
                float(frame.time) if frame.time is not None else decoded_index / fallback_rate
            )
            decoded_index += 1
            if frame_time + 1e-6 < source_start_seconds:
                continue
            relative_time = frame_time - source_start_seconds
            image = _fit_frame(frame, width, height)
            if last_image is None:
                last_image = image
            while target_index < frame_count and target_index / frames_per_second < relative_time:
                yield last_image
                target_index += 1
            last_image = image
            if target_index >= frame_count:
                break

    if last_image is None:
        raise ValueError(f"Kinebeat could not decode frames from {source.name}.")
    while target_index < frame_count:
        yield last_image
        target_index += 1


def _fit_frame(frame: av.VideoFrame, width: int, height: int) -> np.ndarray:
    scale = min(width / frame.width, height / frame.height)
    scaled_width = max(2, round(frame.width * scale / 2) * 2)
    scaled_height = max(2, round(frame.height * scale / 2) * 2)
    image = frame.reformat(width=scaled_width, height=scaled_height, format="rgb24").to_ndarray()
    canvas = np.full((height, width, 3), 7, dtype=np.uint8)
    left = max(0, (width - scaled_width) // 2)
    top = max(0, (height - scaled_height) // 2)
    visible_width = min(width, scaled_width)
    visible_height = min(height, scaled_height)
    canvas[top : top + visible_height, left : left + visible_width] = image[
        :visible_height, :visible_width
    ]
    return canvas


def _clock(seconds: float) -> str:
    minutes, whole_seconds = divmod(max(0, round(seconds)), 60)
    return f"{minutes}:{whole_seconds:02d}"
