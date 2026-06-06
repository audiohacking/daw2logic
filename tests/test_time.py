"""Tests for beat/tick and velocity conversion."""

from daw2logic.ir import MeterPoint, TempoPoint, Transport
from daw2logic.time import PPQ, beats_to_tick, build_time_map, velocity_to_midi


def test_beats_to_tick_quarter_notes():
    assert beats_to_tick(0.0) == 0
    assert beats_to_tick(1.0) == PPQ
    assert beats_to_tick(0.5) == PPQ // 2


def test_velocity_to_midi():
    assert velocity_to_midi(0.0) == 1
    assert velocity_to_midi(1.0) == 127
    assert velocity_to_midi(0.787402) == 100


def test_time_map_meter_change():
    transport = Transport(
        tempo=120.0,
        numerator=4,
        denominator=4,
        tempo_map=(TempoPoint(0.0, 120.0),),
        meter_map=(
            MeterPoint(0.0, 4, 4),
            MeterPoint(4.0, 3, 4),
        ),
    )
    time_map = build_time_map(transport)
    assert beats_to_tick(4.0, time_map) == 3840
    assert beats_to_tick(5.0, time_map) == 3840 + 960
