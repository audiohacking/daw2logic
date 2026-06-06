"""Tests for DAWproject parsing."""

from daw2logic.parser import cleanup, load


def test_load_bitwig_simple_transport(bitwig_simple_dawproject):
    project = load(bitwig_simple_dawproject)
    try:
        assert project.transport.tempo == 149.0
        assert project.transport.numerator == 4
        assert project.transport.denominator == 4
    finally:
        cleanup(project)


def test_load_bitwig_simple_tracks(bitwig_simple_dawproject):
    project = load(bitwig_simple_dawproject)
    try:
        names = {t.name for t in project.tracks}
        assert names == {"Bass", "Drumloop"}
    finally:
        cleanup(project)


def test_load_bitwig_simple_midi_notes(bitwig_simple_dawproject):
    project = load(bitwig_simple_dawproject)
    try:
        bass = next(t for t in project.tracks if t.name == "Bass")
        assert len(bass.midi_clips) == 1
        notes = bass.midi_clips[0].notes
        assert len(notes) == 3
        pitches = {n.pitch for n in notes}
        assert pitches == {64, 65}
    finally:
        cleanup(project)


def test_load_bitwig_simple_nested_audio(bitwig_simple_dawproject):
    project = load(bitwig_simple_dawproject)
    try:
        drums = next(t for t in project.tracks if t.name == "Drumloop")
        assert len(drums.audio_clips) == 1
        clip = drums.audio_clips[0]
        assert clip.path == "audio/white-glasses.wav"
        assert clip.start == 0.0
        assert clip.sample_rate == 48000
    finally:
        cleanup(project)
