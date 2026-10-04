"""Media-only readiness and explicitly synthetic one-pass consumption metrics."""
from __future__ import annotations
import re
from .contracts import Readiness
from .errors import AppError


def required_media(short, data, assets):
    """Publication metadata plus durable audio and every essential managed image.

    Speech validates measured audio/boundaries before publication. Here we check
    continued file availability; this is not a guarantee against later deletion.
    """
    if not short.audio_path or not re.fullmatch(r"[a-f0-9]{64}\.wav", short.audio_path):
        raise AppError("AUDIO_NOT_FOUND", "The audio file is missing. Retry to repair this short.", 404)
    path = data / "audio" / short.audio_path
    if not path.is_file() or path.is_symlink() or path.stat().st_size < 44:
        raise AppError("AUDIO_NOT_FOUND", "The audio file is missing. Retry to repair this short.", 404)
    if not short.scenes or not short.narration_units or short.measured_duration_ms <= 0:
        raise AppError("PLAYBACK_METADATA_MISSING", "Playback metadata is incomplete. Retry lesson preparation.", 422)
    for scene in short.scenes:
        if scene.kind == "image":
            assets.attach(scene.payload.asset_id)


def contiguous_media(shorts, active_id=None, position_ms=0, ready_ids=None):
    """Remaining current media + following ready media, stopping at the first gap.

    Never includes question allowances or repeated loops. Seeking/jumping simply
    changes the origin. Pause freezes position, not authorised generation.
    """
    start = next((i for i, s in enumerate(shorts) if s.id == active_id), 0)
    total = 0
    for i, short in enumerate(shorts[start:], start):
        if short.status != "ready" or (ready_ids is not None and short.id not in ready_ids):
            break
        total += max(0, short.measured_duration_ms - (max(0, position_ms) if i == start else 0))
    return total


def snapshot_readiness(lesson, data, assets):
    ready, missing = [], []
    for short in lesson.shorts:
        if short.status == "ready":
            try:
                required_media(short, data, assets)
                ready.append(short.id)
            except (AppError, OSError):
                missing.append(short.id)
    return Readiness(ready_short_ids=ready, missing_media_short_ids=missing,
                     initial_contiguous_media_ms=contiguous_media(lesson.shorts, ready_ids=set(ready)))


def simulate_one_pass(publications, durations, buffer_ms=0):
    """Deterministic offline benchmark; NOT the looping player's behaviour.

    Publication times are elapsed monotonic seconds; durations are measured ms.
    Start at first playable, or an optional *experimental* initial buffer. No
    question time, pauses, seeks or replay credit. Stalls delay subsequent starts.
    """
    if len(publications) != len(durations) or any(d <= 0 for d in durations):
        raise ValueError("Every publication requires a positive measured duration.")
    if not publications:
        return {"startup_seconds": None, "experimental_buffer_reached_seconds": None, "stalls_seconds": [], "ready_ahead_ms": []}
    cursor = publications[0]
    buffer_reached = None
    if buffer_ms:
        accumulated = 0
        for publication, duration in zip(publications, durations):
            cursor = max(cursor, publication)
            accumulated += duration
            if accumulated >= buffer_ms:
                buffer_reached = cursor
                break
        # If the final lesson is shorter than the hypothesis, this simulation
        # starts with all content; it never claims the requested buffer was met.
    startup = cursor
    stalls, ahead = [], []
    for i, duration in enumerate(durations):
        wait = max(0, publications[i] - cursor)
        cursor += wait
        stalls.append(wait)
        contiguous = 0
        for j in range(i, len(durations)):
            if publications[j] > cursor:
                break
            contiguous += durations[j]
        ahead.append(contiguous)
        cursor += duration / 1000
    return {"startup_seconds": startup, "experimental_buffer_reached_seconds": buffer_reached,
            "stalls_seconds": stalls, "ready_ahead_ms": ahead}
