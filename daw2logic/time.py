"""Musical time conversion between DAWproject and Logic."""

from __future__ import annotations

from logicx.projectdata import TimeMap

from .ir import MeterPoint, TempoPoint, Transport

PPQ = 960


def build_time_map(transport: Transport) -> TimeMap:
    """Build a Logic TimeMap from DAWproject transport data."""
    tempo_pts = transport.tempo_map or (TempoPoint(0.0, transport.tempo),)
    meter_pts = transport.meter_map or (
        MeterPoint(0.0, transport.numerator, transport.denominator),
    )
    return TimeMap(
        tempo_map=[(beats_to_tick(p.time), p.bpm) for p in tempo_pts],
        meter_map=[
            (beats_to_tick(p.time), p.numerator, p.denominator) for p in meter_pts
        ],
        ppq=PPQ,
    )


def beats_to_tick(beats: float, time_map: TimeMap | None = None) -> int:
    """Map DAWproject beat time to Logic 960-PPQ ticks (bar 1 beat 1 = 0)."""
    if time_map is None:
        return int(round(beats * PPQ))
    bar, beat = _beats_to_bar_beat(beats, time_map)
    return time_map.bar_beat_to_tick(bar, beat)


def beats_to_note_tick(beats: float) -> int:
    """Map beat offset inside a region to region-relative Logic ticks."""
    return int(round(beats * PPQ))


def velocity_to_midi(velocity: float) -> int:
    """DAWproject uses 0..1; Logic note events use 0..127."""
    return max(1, min(127, int(round(velocity * 127))))


def beats_to_seconds(beats: float, transport: Transport) -> float:
    """Elapsed seconds at `beats` using the transport tempo map."""
    time_map = build_time_map(transport)
    return time_map.tick_to_seconds(beats_to_tick(beats, time_map))


def _beats_to_bar_beat(beats: float, time_map: TimeMap) -> tuple[float, float]:
    """Convert linear quarter-note beats from song start to bar/beat."""
    if beats <= 0:
        return 1.0, 1.0
    tick = int(round(beats * PPQ))
    bar, beat = time_map.tick_to_bar_beat(tick)
    return float(bar), float(beat)
