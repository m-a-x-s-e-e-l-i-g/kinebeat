from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable
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
) -> GeneratedTimeline:
    """Build a deterministic clip timeline with cuts on detected kicks."""
    if not video_paths:
        raise ValueError("Import at least one video clip before generating a video edit.")

    progress(5, "Finding kick cut points")
    cut_points = _kick_cut_points(analysis)
    segment_count = len(cut_points) - 1
    progress(12, f"Building {segment_count} beat-synced edits")

    rng = random.Random(seed)
    usage: Counter[Path] = Counter()
    clips: list[TimelineClip] = []
    previous_path: Path | None = None
    for index, (start, end) in enumerate(zip(cut_points, cut_points[1:], strict=False)):
        if cancelled():
            raise RuntimeError("Video-edit generation was cancelled.")
        source = _select_source(
            video_paths,
            strategy=strategy,
            index=index,
            previous_path=previous_path,
            usage=usage,
            rng=rng,
        )
        clips.append(TimelineClip(source, start, end))
        usage[source] += 1
        previous_path = source
        value = 12 + round(82 * (index + 1) / segment_count)
        progress(value, f"Placing edit {index + 1} of {segment_count}")

    progress(100, f"Video edit ready · {segment_count} edits")
    return GeneratedTimeline(tuple(clips), seed)


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
