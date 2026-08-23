from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass

import numpy as np

from kinebeat.domain import (
    DEFAULT_EFFECT_MAPPINGS,
    EffectAction,
    EventKind,
    InstrumentMapping,
    MusicAnalysis,
)

_EFFECT_DURATIONS = {
    EffectAction.RANDOM_EFFECT: 0.28,
    EffectAction.ADD_INTENSITY: 0.32,
    EffectAction.ADD_AMBIANCE: 0.70,
    EffectAction.LIGHT_EFFECT: 0.20,
    EffectAction.TIME_BEND: 0.36,
    EffectAction.GLITCH: 0.28,
    EffectAction.VHS: 0.65,
    EffectAction.SILHOUETTE_STRETCH: 0.38,
    EffectAction.VIDEO_VOLUME: 0.46,
    EffectAction.DATAMOSH: 0.55,
}
_RANDOM_EFFECTS = (
    EffectAction.GLITCH,
    EffectAction.VHS,
    EffectAction.SILHOUETTE_STRETCH,
    EffectAction.VIDEO_VOLUME,
    EffectAction.DATAMOSH,
    EffectAction.TIME_BEND,
)
_EVENT_ORDER = {kind: index for index, kind in enumerate(EventKind)}
_ACTION_ORDER = {action: index for index, action in enumerate(EffectAction)}


@dataclass(frozen=True, slots=True)
class EffectCue:
    action: EffectAction
    instrument: EventKind
    start_seconds: float
    end_seconds: float
    intensity: float
    seed: int

    def amount_at(self, timestamp_seconds: float) -> float:
        if not self.start_seconds <= timestamp_seconds < self.end_seconds:
            return 0.0
        duration = max(self.end_seconds - self.start_seconds, 1e-6)
        progress = (timestamp_seconds - self.start_seconds) / duration
        envelope = math.sin(math.pi * progress) ** 0.55
        return float(np.clip(self.intensity * envelope, 0.0, 1.0))


def build_effect_cues(
    analysis: MusicAnalysis,
    mappings: tuple[InstrumentMapping, ...] = DEFAULT_EFFECT_MAPPINGS,
    *,
    seed: int,
) -> tuple[EffectCue, ...]:
    actions = {mapping.instrument: mapping.action for mapping in mappings}
    cues: list[EffectCue] = []
    for index, event in enumerate(analysis.events):
        mapped_action = actions.get(event.kind, EffectAction.NO_ACTION)
        if mapped_action in {EffectAction.CUT, EffectAction.NO_ACTION}:
            continue
        cue_seed = _cue_seed(seed, event.kind, mapped_action, event.timestamp_seconds, index)
        action = mapped_action
        if action is EffectAction.RANDOM_EFFECT:
            action = random.Random(cue_seed).choice(_RANDOM_EFFECTS)
        duration = _EFFECT_DURATIONS[mapped_action]
        cues.append(
            EffectCue(
                action=action,
                instrument=event.kind,
                start_seconds=event.timestamp_seconds,
                end_seconds=min(
                    analysis.song.duration_seconds,
                    event.timestamp_seconds + duration,
                ),
                intensity=0.55 + event.confidence * 0.45,
                seed=cue_seed,
            )
        )
    return tuple(sorted(cues, key=lambda cue: (cue.start_seconds, cue.seed)))


class VideoEffectProcessor:
    def __init__(
        self,
        cues: tuple[EffectCue, ...],
        *,
        frames_per_second: int,
        history_seconds: float = 0.75,
    ) -> None:
        self._cues = cues
        self._frames_per_second = frames_per_second
        self._history: deque[np.ndarray] = deque(
            maxlen=max(3, round(frames_per_second * history_seconds))
        )
        self._next_cue = 0
        self._active: list[EffectCue] = []
        self._previous_source: np.ndarray | None = None
        self._previous_output: np.ndarray | None = None

    def process(self, frame: np.ndarray, timestamp_seconds: float) -> np.ndarray:
        source = np.asarray(frame, dtype=np.uint8)
        while (
            self._next_cue < len(self._cues)
            and self._cues[self._next_cue].start_seconds <= timestamp_seconds
        ):
            self._active.append(self._cues[self._next_cue])
            self._next_cue += 1
        self._active = [cue for cue in self._active if cue.end_seconds > timestamp_seconds]

        result = source.copy()
        history = tuple(self._history)
        for cue in self._active:
            amount = cue.amount_at(timestamp_seconds)
            if amount <= 0.001:
                continue
            frame_seed = cue.seed ^ round(timestamp_seconds * self._frames_per_second)
            rng = np.random.default_rng(frame_seed)
            result = _apply_effect(
                result,
                cue.action,
                amount,
                history,
                self._previous_source,
                self._previous_output,
                rng,
            )

        self._history.append(source.copy())
        self._previous_source = source.copy()
        self._previous_output = result.copy()
        return result


def _apply_effect(
    frame: np.ndarray,
    action: EffectAction,
    amount: float,
    history: tuple[np.ndarray, ...],
    previous_source: np.ndarray | None,
    previous_output: np.ndarray | None,
    rng: np.random.Generator,
) -> np.ndarray:
    if action is EffectAction.GLITCH:
        return _glitch(frame, amount, rng)
    if action is EffectAction.VHS:
        return _vhs(frame, amount, rng)
    if action is EffectAction.SILHOUETTE_STRETCH:
        return _silhouette_stretch(frame, previous_source, amount)
    if action is EffectAction.VIDEO_VOLUME:
        return _video_volume(frame, history, amount)
    if action is EffectAction.DATAMOSH:
        return _datamosh(frame, previous_source, previous_output, amount, rng)
    if action is EffectAction.TIME_BEND:
        return _time_bend(frame, history, amount)
    if action is EffectAction.ADD_INTENSITY:
        return _intensity(frame, amount)
    if action is EffectAction.ADD_AMBIANCE:
        return _ambiance(frame, history, amount)
    if action is EffectAction.LIGHT_EFFECT:
        return _light_flash(frame, amount)
    return frame


def _glitch(frame: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
    height, width = frame.shape[:2]
    result = frame.copy()
    max_shift = max(2, round(width * (0.012 + amount * 0.055)))
    for _ in range(2 + round(amount * 7)):
        top = int(rng.integers(0, max(1, height - 2)))
        band_height = int(rng.integers(2, max(3, height // 9)))
        bottom = min(height, top + band_height)
        shift = int(rng.integers(-max_shift, max_shift + 1))
        result[top:bottom] = np.roll(result[top:bottom], shift, axis=1)
    channel_shift = max(1, round(max_shift * 0.55))
    result[..., 0] = np.roll(result[..., 0], channel_shift, axis=1)
    result[..., 2] = np.roll(result[..., 2], -channel_shift, axis=1)
    if amount > 0.58:
        block_height = max(2, height // 18)
        top = int(rng.integers(0, max(1, height - block_height)))
        result[top : top + block_height, :, 1] = 255 - result[top : top + block_height, :, 1]
    return result


def _vhs(frame: np.ndarray, amount: float, rng: np.random.Generator) -> np.ndarray:
    height, width = frame.shape[:2]
    result = frame.astype(np.float32)
    jittered = result.copy()
    stripe = max(3, height // 32)
    for top in range(0, height, stripe):
        shift = int(rng.integers(-2, 3) * max(1.0, amount * 2.5))
        jittered[top : top + stripe] = np.roll(result[top : top + stripe], shift, axis=1)
    chroma = max(1, round(width * 0.008 * amount))
    jittered[..., 0] = np.roll(jittered[..., 0], chroma, axis=1)
    jittered[..., 2] = np.roll(jittered[..., 2], -chroma, axis=1)
    scanlines = np.ones((height, 1, 1), dtype=np.float32)
    scanlines[1::2] = 1.0 - 0.14 * amount
    noise = rng.normal(0.0, 5.0 + amount * 9.0, result.shape[:2])[..., None]
    jittered = jittered * scanlines + noise
    tracking_y = int(rng.integers(0, height))
    tracking_height = max(2, round(height * 0.025))
    jittered[tracking_y : tracking_y + tracking_height] += 28.0 * amount
    jittered[..., 1] *= 1.0 + 0.05 * amount
    return np.clip(jittered, 0, 255).astype(np.uint8)


def _intensity(frame: np.ndarray, amount: float) -> np.ndarray:
    pixels = frame.astype(np.float32)
    luma = pixels.mean(axis=2, keepdims=True)
    saturated = luma + (pixels - luma) * (1.0 + amount * 0.8)
    contrasted = (saturated - 127.5) * (1.0 + amount * 0.42) + 127.5
    return np.clip(contrasted + amount * 8.0, 0, 255).astype(np.uint8)


def _ambiance(frame: np.ndarray, history: tuple[np.ndarray, ...], amount: float) -> np.ndarray:
    if not history:
        return frame
    past = history[max(0, len(history) - 5)].astype(np.float32)
    current = frame.astype(np.float32)
    ghost = np.roll(past, max(1, round(frame.shape[1] * 0.012)), axis=1)
    mixed = current * (1.0 - amount * 0.28) + ghost * amount * 0.28
    mixed[..., 0] = np.roll(mixed[..., 0], 2, axis=1)
    mixed[..., 2] = np.roll(mixed[..., 2], -2, axis=1)
    return np.clip(mixed, 0, 255).astype(np.uint8)


def _light_flash(frame: np.ndarray, amount: float) -> np.ndarray:
    height = frame.shape[0]
    y = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None, None]
    band = np.exp(-(y * y) / 0.16)
    pixels = frame.astype(np.float32)
    flashed = pixels + (255.0 - pixels) * amount * (0.25 + band * 0.55)
    return np.clip(flashed, 0, 255).astype(np.uint8)


def _time_bend(frame: np.ndarray, history: tuple[np.ndarray, ...], amount: float) -> np.ndarray:
    frames = (*history[-10:], frame)
    if len(frames) < 3:
        return frame
    stack = np.stack(frames)
    luma = (
        frame[..., 0].astype(np.float32) * 0.2126
        + frame[..., 1].astype(np.float32) * 0.7152
        + frame[..., 2].astype(np.float32) * 0.0722
    )
    depth = max(2, round((len(stack) - 1) * amount))
    indices = len(stack) - 1 - np.rint(luma / 255.0 * depth).astype(np.intp)
    indices = np.clip(indices, 0, len(stack) - 1)
    rows, columns = np.indices(frame.shape[:2])
    return stack[indices, rows, columns]


def _video_volume(frame: np.ndarray, history: tuple[np.ndarray, ...], amount: float) -> np.ndarray:
    frames = (*history[-14:], frame)
    if len(frames) < 3:
        return frame
    stack = np.stack(frames)
    height, width = frame.shape[:2]
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    surface = x * (0.65 + amount * 0.35) + np.sin(y * math.tau * 1.5) * amount * 0.18
    scaled = np.clip(surface, 0.0, 1.0) * (len(stack) - 1)
    before = np.floor(scaled).astype(np.intp)
    after = np.minimum(before + 1, len(stack) - 1)
    blend = (scaled - before)[..., None]
    rows, columns = np.indices((height, width))
    sampled = (
        stack[before, rows, columns].astype(np.float32) * (1.0 - blend)
        + stack[after, rows, columns].astype(np.float32) * blend
    )
    return np.clip(sampled, 0, 255).astype(np.uint8)


def _silhouette_stretch(
    frame: np.ndarray,
    previous_source: np.ndarray | None,
    amount: float,
) -> np.ndarray:
    height, width = frame.shape[:2]
    pixels = frame.astype(np.float32)
    border = np.concatenate(
        (pixels[0], pixels[-1], pixels[:, 0], pixels[:, -1]),
        axis=0,
    )
    background = np.median(border, axis=0)
    distance = np.linalg.norm(pixels - background, axis=2)
    threshold = max(32.0, float(np.percentile(distance, 76)))
    mask = distance >= threshold
    if previous_source is not None:
        motion = np.mean(
            np.abs(pixels - previous_source.astype(np.float32)),
            axis=2,
        )
        motion_threshold = max(10.0, float(np.percentile(motion, 82)))
        mask |= motion >= motion_threshold
    neighbours = sum(
        np.roll(np.roll(mask, y_shift, axis=0), x_shift, axis=1)
        for y_shift in (-1, 0, 1)
        for x_shift in (-1, 0, 1)
    )
    mask = neighbours >= 5
    if int(mask.sum()) < height * width * 0.01:
        return _glitch(frame, amount * 0.7, np.random.default_rng(0))

    result = pixels.copy()
    opacity = 0.35 + amount * 0.5
    for row in range(height):
        columns = np.flatnonzero(mask[row])
        if not len(columns):
            continue
        left = int(columns[0])
        right = int(columns[-1])
        left_color = pixels[row, min(width - 1, left + 1)]
        right_color = pixels[row, max(0, right - 1)]
        if left > 0:
            fade = np.linspace(0.08, opacity, left, dtype=np.float32)[:, None]
            result[row, :left] = result[row, :left] * (1.0 - fade) + left_color * fade
        if right + 1 < width:
            span = width - right - 1
            fade = np.linspace(opacity, 0.08, span, dtype=np.float32)[:, None]
            result[row, right + 1 :] = result[row, right + 1 :] * (1.0 - fade) + right_color * fade
    result[mask] = pixels[mask]
    shift = max(1, round(width * 0.006 * amount))
    result[..., 0] = np.roll(result[..., 0], shift, axis=1)
    result[..., 2] = np.roll(result[..., 2], -shift, axis=1)
    result[mask] = pixels[mask]
    return np.clip(result, 0, 255).astype(np.uint8)


def _datamosh(
    frame: np.ndarray,
    previous_source: np.ndarray | None,
    previous_output: np.ndarray | None,
    amount: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if previous_source is None or previous_output is None:
        return frame
    height, width = frame.shape[:2]
    carried = np.roll(
        previous_output,
        (int(rng.integers(-3, 4)), int(rng.integers(-8, 9))),
        axis=(0, 1),
    )
    result = frame.copy()
    block = 16
    for top in range(0, height, block):
        for left in range(0, width, block):
            bottom = min(height, top + block)
            right = min(width, left + block)
            difference = np.mean(
                np.abs(
                    frame[top:bottom, left:right].astype(np.int16)
                    - previous_source[top:bottom, left:right].astype(np.int16)
                )
            )
            carry_chance = amount * (0.35 + min(float(difference) / 80.0, 0.65))
            if rng.random() < carry_chance:
                result[top:bottom, left:right] = carried[top:bottom, left:right]
    if amount > 0.65:
        result[..., 1] = np.roll(result[..., 1], round(width * 0.012 * amount), axis=1)
    return result


def _cue_seed(
    seed: int,
    instrument: EventKind,
    action: EffectAction,
    timestamp_seconds: float,
    index: int,
) -> int:
    value = (
        seed * 1_000_003
        + round(timestamp_seconds * 1000) * 9_176
        + _EVENT_ORDER[instrument] * 1_009
        + _ACTION_ORDER[action] * 131
        + index * 37
    )
    return value & 0xFFFFFFFF
