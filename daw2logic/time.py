"""Convert musical time in quarter-note beats to Logic 960-PPQ ticks."""

from __future__ import annotations

PPQ = 960


def beats_to_tick(beats: float) -> int:
    """Map DAWproject beat time (quarter notes from song start) to Logic ticks."""
    return int(round(beats * PPQ))


def beats_to_note_tick(beats: float) -> int:
    """Map beat offset inside a region to region-relative Logic ticks."""
    return beats_to_tick(beats)


def velocity_to_midi(velocity: float) -> int:
    """DAWproject uses 0..1; Logic note events use 0..127."""
    return max(1, min(127, int(round(velocity * 127))))
