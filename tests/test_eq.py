"""Equalizer parsing and Logic Channel EQ mapping tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from daw2logic.eq import equalizer_to_logic_channel_eq, parse_equalizer, semitones_to_hz
from daw2logic.parser import cleanup, load
import xml.etree.ElementTree as ET


def test_semitones_to_hz():
    assert semitones_to_hz(69) == pytest.approx(440.0)
    assert semitones_to_hz(38.431102) == pytest.approx(75.26, rel=0.01)


def test_parse_equalizer_band():
    xml = """
    <Equalizer deviceName="EQ-5" deviceID="abc" deviceRole="audioFX" name="EQ-5">
      <Enabled value="true"/>
      <Band type="bell" order="2">
        <Freq unit="semitones" value="38.431102"/>
        <Gain unit="decibel" value="5.413534"/>
        <Q unit="linear" value="0.707000"/>
        <Enabled value="true"/>
      </Band>
    </Equalizer>"""
    eq = parse_equalizer(ET.fromstring(xml))
    assert eq.name == "EQ-5"
    assert len(eq.bands) == 1
    assert eq.bands[0].band_type == "bell"
    assert eq.bands[0].gain_db == pytest.approx(5.413534)
    logic = equalizer_to_logic_channel_eq(eq)
    assert logic["target_plugin"] == "Logic Channel EQ"
    assert logic["bands"][0]["logic_type"] == "parametric"
    assert logic["bands"][0]["frequency_hz"] == pytest.approx(75.26, rel=0.01)


def test_grease1_parses_equalizers():
    grease = Path("tmp/GREASE1.dawproject")
    if not grease.is_file():
        pytest.skip("local GREASE1 fixture not present")
    project = load(grease)
    try:
        drums = next(t for t in project.tracks if t.name == "2 Drums")
        assert len(drums.equalizers) == 1
        assert len(drums.equalizers[0].bands) == 5
        vocals = next(t for t in project.tracks if t.name == "0 Lead Vocals")
        assert vocals.equalizers[0].bands[0].band_type == "highPass"
    finally:
        cleanup(project)
