"""Tests for Logic channel mapping and mixer patching."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.logicx_channels import audio_channels, instrument_channels
from daw2logic.mixer_logic import (
    OCUA_AUDIO_VOLUME_DB_OFF,
    OCUA_PAN_OFF,
    OCUA_VOL_GATE_OFF,
    OCUA_VOLUME_DB_OFFSET,
    apply_mixer,
    linear_to_logic_volume_db,
    logic_pan_byte_to_normalized,
    logic_volume_db_to_linear,
    normalized_to_logic_pan_byte,
    patch_ocua_mixer,
)
from logicx.projectdata import ProjectData, _ocua_for_channel


def test_instrument_and_audio_channel_maps(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    inst = instrument_channels(pd)
    aud = audio_channels(pd)
    assert 1 in inst and 1 in aud
    assert inst[1] != aud[1]


def test_patch_ocua_mixer_inactive_strip():
    inactive = b"\x00" * 205
    assert patch_ocua_mixer(inactive, volume_linear=0.5) is None


def test_volume_db_encoding_from_logic_capture():
    """Logic -6 dB capture stored float 1.559 @0x98."""
    stored = linear_to_logic_volume_db(10 ** (-6 / 20))
    assert stored == pytest.approx(1.5590658, rel=1e-4)
    assert logic_volume_db_to_linear(stored) == pytest.approx(0.501187, rel=1e-3)


def test_convert_patches_drumloop_volume(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    ch = audio_channels(pd)[2]  # synthesized Drumloop (ordinal 2)
    oc = _ocua_for_channel(pd, ch)
    stored = struct.unpack_from("<f", oc.raw, OCUA_AUDIO_VOLUME_DB_OFF)[0]
    expected = linear_to_logic_volume_db(0.177125)
    assert stored == pytest.approx(expected, rel=1e-4)
    assert "Drumloop" in report.mixer_patched_tracks


def test_convert_patches_bass_volume(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    ch = instrument_channels(pd)[2]  # synthesized Bass (ordinal 2)
    oc = _ocua_for_channel(pd, ch)
    stored = struct.unpack_from("<f", oc.raw, OCUA_AUDIO_VOLUME_DB_OFF)[0]
    expected = linear_to_logic_volume_db(0.659140)
    assert stored == pytest.approx(expected, rel=1e-4)
    assert oc.raw[OCUA_VOL_GATE_OFF] == 0x3F
    assert "Bass" in report.mixer_patched_tracks
    assert "Drumloop" in report.mixer_patched_tracks
    assert not any("mixer values exported to sidecar" in w and "Bass" in w for w in report.warnings)
    assert not any("track 'Drumloop': mixer values exported to sidecar" in w for w in report.warnings)


def test_bitwig_mixer_fixture_parsed(bitwig_mixer_dawproject):
    from daw2logic.parser import load

    project = load(bitwig_mixer_dawproject)
    bass = next(t for t in project.tracks if t.name == "Bass")
    drum = next(t for t in project.tracks if t.name == "Drumloop")
    assert bass.mute is True
    assert bass.pan == pytest.approx(0.25)
    assert drum.pan == pytest.approx(0.75)
    assert drum.mute is False


def test_pan_byte_encoding_from_logic_capture():
    assert normalized_to_logic_pan_byte(0.0) == 0
    assert normalized_to_logic_pan_byte(0.5) == 64
    assert normalized_to_logic_pan_byte(1.0) == 127
    assert logic_pan_byte_to_normalized(0) == pytest.approx(0.0)
    assert logic_pan_byte_to_normalized(64) == pytest.approx(64 / 127)


def test_bitwig_mixer_exports_pan_mute_sidecar(bitwig_mixer_dawproject, logicx_output):
    import json

    report = convert_file(bitwig_mixer_dawproject, logicx_output)
    assert "Bass" in report.mixer_patched_tracks
    assert "Drumloop" in report.mixer_patched_tracks
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    drum_raw = _ocua_for_channel(pd, audio_channels(pd)[2]).raw
    bass_raw = _ocua_for_channel(pd, instrument_channels(pd)[2]).raw
    assert drum_raw[OCUA_PAN_OFF] == normalized_to_logic_pan_byte(0.75)
    assert bass_raw[OCUA_PAN_OFF] == normalized_to_logic_pan_byte(0.25)
    manifest = json.loads(
        (logicx_output / "Media/daw2logic Import/manifest.json").read_text()
    )
    bass = next(t for t in manifest["tracks"] if t["name"] == "Bass")
    drum = next(t for t in manifest["tracks"] if t["name"] == "Drumloop")
    assert bass["mixer"]["mute"] is True
    assert bass["mixer"]["pan_normalized"] == pytest.approx(0.25)
    assert drum["mixer"]["pan_normalized"] == pytest.approx(0.75)


def test_logic_re_pan_fixture_if_present():
    base = Path("/tmp/daw2logic-re/mixer_baseline.logicx")
    pan = Path("/tmp/daw2logic-re/drumloop_pan_left.logicx")
    if not (base / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic pan baseline fixture")
    if not (pan / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic pan capture")
    pd0 = ProjectData.parse((base / "Alternatives/000/ProjectData").read_bytes())
    pd1 = ProjectData.parse((pan / "Alternatives/000/ProjectData").read_bytes())
    ch = audio_channels(pd0)[2]
    b0 = _ocua_for_channel(pd0, ch).raw[OCUA_PAN_OFF]
    b1 = _ocua_for_channel(pd1, ch).raw[OCUA_PAN_OFF]
    assert b0 == normalized_to_logic_pan_byte(0.5)
    assert b1 == normalized_to_logic_pan_byte(0.0)


def test_logic_re_fixture_if_present():
    """Optional: validate against /tmp/daw2logic-re Logic differential."""
    base = Path("/tmp/daw2logic-re/re.logicx")
    vol = Path("/tmp/daw2logic-re/re_vol.logicx")
    if not (base / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic RE fixture")
    if not (vol / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic RE after-volume fixture")
    pd0 = ProjectData.parse((base / "Alternatives/000/ProjectData").read_bytes())
    pd1 = ProjectData.parse((vol / "Alternatives/000/ProjectData").read_bytes())
    # Audio 1 template strip received -6 dB in user's capture (track mix-up in UI).
    ch = audio_channels(pd0)[1]
    s1 = struct.unpack_from("<f", _ocua_for_channel(pd1, ch).raw, OCUA_AUDIO_VOLUME_DB_OFF)[0]
    assert s1 == pytest.approx(linear_to_logic_volume_db(10 ** (-6 / 20)), rel=1e-3)
    assert s1 - OCUA_VOLUME_DB_OFFSET == pytest.approx(-6.0, abs=0.05)
