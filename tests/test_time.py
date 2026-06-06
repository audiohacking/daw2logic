"""Tests for beat/tick and velocity conversion."""

from daw2logic.time import PPQ, beats_to_tick, velocity_to_midi


def test_beats_to_tick_quarter_notes():
    assert beats_to_tick(0.0) == 0
    assert beats_to_tick(1.0) == PPQ
    assert beats_to_tick(0.5) == PPQ // 2


def test_velocity_to_midi():
    assert velocity_to_midi(0.0) == 1
    assert velocity_to_midi(1.0) == 127
    assert velocity_to_midi(0.787402) == 100
