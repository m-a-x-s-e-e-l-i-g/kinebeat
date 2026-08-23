from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Mapping
from pathlib import Path

from kinebeat.domain import EventKind, GeneratedTimeline, MusicAnalysis, TimelineClip

ProgressCallback = Callable[[int, str], None]
CancelCheck = Callable[[], bool]


def generate_first_cut(
    analysis: MusicAnalysis,
    video_paths: tuple[Path, ...],
    *,
    strategy: str,
    seed: int,
    progress: ProgressCallback,
    cancelled: CancelCheck,
    source_durations: Mapping[Path, float] | None = None,
) -> GeneratedTimeline:
    """Build a deterministic clip timeline without reusing source ranges."""
    if not video_paths:
        raise ValueError("Import at least one video clip before generating a video edit.")

    progress(5, "Finding kick cut points")
    cut_points = _kick_cut_points(analysis)
    segment_count = len(cut_points) - 1
    progress(12, f"Building {segment_count} beat-synced edits")

    rng = random.Random(seed)
    usage: Counter[Path] = Counter()
    source_cursors = {path: 0.0 for path in video_paths}
    clips: list[TimelineClip] = []
    previous_path: Path | None = None
    for index, (start, end) in enumerate(zip(cut_points, cut_points[1:], strict=False)):
        if cancelled():
            raise RuntimeError("Video-edit generation was cancelled.")
        segment_duration = end - start
        eligible_paths = tuple(
            path
            for path in video_paths
            if source_durations is None
            or source_cursors[path] + segment_duration
            <= source_durations.get(path, 0.0) + 1e-6
        )
        if not eligible_paths:
            raise ValueError(
                _unused_footage_error(
                    analysis.song.duration_seconds,
                    start,
                    segment_duration,
                    source_cursors,
                    source_durations,
                )
            )
        source = _select_source(
            eligible_paths,
            strategy=strategy,
            index=index,
            previous_path=previous_path,
            usage=usage,
            rng=rng,
        )
        source_start = source_cursors[source]
        clips.append(
            TimelineClip(
                source,
                start,
                end,
                source_start_seconds=source_start,
            )
        )
        source_cursors[source] += segment_duration
        usage[source] += 1
        previous_path = source
        value = 12 + round(82 * (index + 1) / segment_count)
        progress(value, f"Placing edit {index + 1} of {segment_count}")

    progress(100, f"Video edit ready · {segment_count} edits")
    return GeneratedTimeline(tuple(clips), seed)


def _unused_footage_error(
    song_duration: float,
    timeline_start: float,
    segment_duration: float,
    source_cursors: Mapping[Path, float],
    source_durations: Mapping[Path, float] | None,
) -> str:
    if source_durations is None:
        return "Kinebeat could not allocate an unused part of the imported footage."

    remaining = {
        path: max(0.0, source_durations.get(path, 0.0) - cursor)
        for path, cursor in source_cursors.items()
    }
    total_remaining = sum(remaining.values())
    longest_remaining = max(remaining.values(), default=0.0)
    timeline_remaining = song_duration - timeline_start
    extra_needed = max(
        timeline_remaining - total_remaining,
        segment_duration - longest_remaining,
        0.1,
    )
    return (
        f"Kinebeat ran out of unused footage at {_clock(timeline_start)}. "
        f"Add at least {extra_needed:.1f} seconds of new or longer footage. "
        "Already-used parts will not be repeated."
    )


def _clock(seconds: float) -> str:
    minutes, whole_seconds = divmod(max(0, round(seconds)), 60)
    return f"{minutes}:{whole_seconds:02d}"


def _kick_cut_points(analysis: MusicAnalysis) -> tuple[float, ...]:
    duration = analysis.song.duration_seconds
    kicks = sorted(
        {
            event.timestamp_seconds
            for event in analysis.events_for(EventKind.KICK)
            if 0.08 < event.timestamp_seconds < duration - 0.08
        }
    )
    return (0.0, *kicks, duration)


def _select_source(
    paths: tuple[Path, ...],
    *,
    strategy: str,
    index: int,
    previous_path: Path | None,
    usage: Counter[Path],
    rng: random.Random,
) -> Path:
    if strategy == "Random":
        choices = [path for path in paths if path != previous_path] or list(paths)
        return rng.choice(choices)
    if strategy == "Least used first":
        minimum = min(usage[path] for path in paths)
        choices = [path for path in paths if usage[path] == minimum]
        return rng.choice(choices)
    if strategy == "Movement based":
        # Motion scoring will replace this seeded ordering once footage analysis lands.
        offset = rng.randrange(len(paths)) if index == 0 else 0
        return paths[(index + offset) % len(paths)]
    return paths[index % len(paths)]
