"""Tests for Logic channel mapping and mixer patching."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.logicx_channels import audio_channels, instrument_channels
from daw2logic.mixer_logic import (
    OCUA_AUDIO_VOLUME_DB_OFF,
    OCUA_VOLUME_DB_OFFSET,
    apply_mixer,
    linear_to_logic_volume_db,
    logic_volume_db_to_linear,
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


def test_convert_bass_volume_still_sidecar(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    assert "Drumloop" in report.mixer_patched_tracks
    assert "Bass" not in report.mixer_patched_tracks
    assert any("instrument strip volume not RE'd" in w for w in report.warnings)
    assert any("track 'Bass': mixer values exported to sidecar" in w for w in report.warnings)
    assert not any("track 'Drumloop': mixer values exported to sidecar" in w for w in report.warnings)


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
