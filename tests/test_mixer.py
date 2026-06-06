"""Tests for Logic channel mapping and mixer patching."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.logicx_channels import audio_channels, instrument_channels
from daw2logic.mixer_logic import (
    OCUA_AUDIO_VOLUME_DB_OFF,
    OCUA_MUTE_OFF,
    OCUA_MUTE_ON,
    OCUA_PAN_OFF,
    OCUA_VOL_GATE_OFF,
    OCUA_VOLUME_DB_OFFSET,
    OCUA_VOLUME_FLOAT_TAIL,
    IVNE_VOLUME_ACTIVE_OFF,
    IVNE_VOLUME_ACTIVE_VAL,
    IVNE_VOLUME_OFF,
    KART_VOL_DISPLAY_OFF,
    apply_mixer,
    encode_ocua_volume,
    encode_ocua_volume_bytes,
    linear_to_ivne_volume_float,
    linear_to_kart_volume_display,
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
    """Logic -6 dB capture from volume_sweep_baseline.logicx."""
    gate, bs = encode_ocua_volume(10 ** (-6 / 20))
    assert gate == 0x3F
    assert bs == bytes.fromhex("3c8fc73f")
    stored = struct.unpack("<f", bs)[0]
    assert stored == pytest.approx(1.5590658, rel=1e-4)
    assert logic_volume_db_to_linear(stored) == pytest.approx(0.501187, rel=1e-3)


def test_encode_ocua_volume_gate_matches_float_tail():
    for linear in (0.659140, 0.177125, 10 ** (-6 / 20), 1.0):
        gate, bs = encode_ocua_volume(linear)
        assert bs[3] == gate


def test_encode_ocua_volume_bass_and_drum():
    gate, bs = encode_ocua_volume(0.659140)  # ~-3.6 dB
    assert gate == 0x49
    assert bs.hex() == "6db4bc49"
    assert bs[3] == gate
    gate, bs = encode_ocua_volume(0.177125)  # ~-15 dB
    assert gate == 0x25
    assert bs.hex() == "3c8fc725"
    assert bs[3] == gate


def test_convert_patches_drumloop_volume(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    ch = audio_channels(pd)[2]  # synthesized Drumloop (ordinal 2)
    oc = _ocua_for_channel(pd, ch)
    raw = oc.raw
    assert raw[OCUA_VOL_GATE_OFF] == 0x25
    assert raw[OCUA_VOLUME_FLOAT_TAIL] == 0x25
    assert raw[OCUA_AUDIO_VOLUME_DB_OFF:OCUA_AUDIO_VOLUME_DB_OFF + 4].hex() == "3c8fc725"
    assert "Drumloop" in report.mixer_patched_tracks


def test_convert_patches_bass_volume(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    ch = instrument_channels(pd)[2]  # synthesized Bass (ordinal 2)
    oc = _ocua_for_channel(pd, ch)
    raw = oc.raw
    assert raw[OCUA_VOL_GATE_OFF] == 0x49
    assert raw[OCUA_VOLUME_FLOAT_TAIL] == 0x49
    assert raw[OCUA_AUDIO_VOLUME_DB_OFF:OCUA_AUDIO_VOLUME_DB_OFF + 4].hex() == "6db4bc49"
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


def test_kart_volume_display_encoding_from_logic_capture():
    assert linear_to_kart_volume_display(10 ** (-6 / 20)) == pytest.approx(-6 / 17, rel=1e-4)
    assert linear_to_kart_volume_display(1.0) == 0.0


def test_ivne_volume_encoding_from_logic_capture():
    assert linear_to_ivne_volume_float(10 ** (-6 / 20)) == pytest.approx(0.015348792, rel=1e-5)
    assert linear_to_ivne_volume_float(1.0) == 0.0


def test_convert_patches_kart_display_volume(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    drum_ch = audio_channels(pd)[2]
    drum_kart = next(
        r for r in pd.records
        if r.tag == b"karT" and len(r.raw) == 93
        and int.from_bytes(r.raw[8:12], "little") == 0x040000
        and int.from_bytes(r.raw[0x2A:0x2E], "little") == drum_ch
    )
    stored = struct.unpack_from("<f", drum_kart.raw, KART_VOL_DISPLAY_OFF)[0]
    assert stored == pytest.approx(linear_to_kart_volume_display(0.177125), rel=1e-4)
    assert drum_kart.raw[0x26] == 0x14
    assert drum_kart.raw[0x4F] == 0x0C


def test_convert_patches_ivne_display_volume(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    drum_ch = audio_channels(pd)[2]
    drum_iv = next(
        r for r in pd.records
        if r.tag == b"ivnE" and int.from_bytes(r.raw[8:12], "little") == drum_ch
    )
    stored = struct.unpack_from("<f", drum_iv.raw, IVNE_VOLUME_OFF)[0]
    assert stored == pytest.approx(linear_to_ivne_volume_float(0.177125), rel=1e-4)
    assert drum_iv.raw[IVNE_VOLUME_ACTIVE_OFF] == IVNE_VOLUME_ACTIVE_VAL


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
    assert bass_raw[OCUA_MUTE_OFF] == OCUA_MUTE_ON
    assert drum_raw[OCUA_MUTE_OFF] == 0
    manifest = json.loads(
        (logicx_output / "Media/daw2logic Import/manifest.json").read_text()
    )
    bass = next(t for t in manifest["tracks"] if t["name"] == "Bass")
    drum = next(t for t in manifest["tracks"] if t["name"] == "Drumloop")
    assert bass["mixer"]["mute"] is True
    assert bass["mixer"]["pan_normalized"] == pytest.approx(0.25)
    assert drum["mixer"]["pan_normalized"] == pytest.approx(0.75)


def test_logic_re_volume_fixture_if_present():
    vol = Path("/tmp/daw2logic-re/drumloop_minus6db.logicx")
    if not (vol / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic -6 dB volume capture")
    pd1 = ProjectData.parse((vol / "Alternatives/000/ProjectData").read_bytes())
    ch = audio_channels(pd1)[2]
    drum_kart = next(
        r for r in pd1.records
        if r.tag == b"karT" and len(r.raw) == 93
        and int.from_bytes(r.raw[8:12], "little") == 0x040000
        and int.from_bytes(r.raw[0x2A:0x2E], "little") == ch
    )
    stored = struct.unpack_from("<f", drum_kart.raw, KART_VOL_DISPLAY_OFF)[0]
    assert stored == pytest.approx(-6 / 17, rel=1e-3)
    drum_iv = next(
        r for r in pd1.records
        if r.tag == b"ivnE" and int.from_bytes(r.raw[8:12], "little") == ch
    )
    iv_stored = struct.unpack_from("<f", drum_iv.raw, IVNE_VOLUME_OFF)[0]
    assert iv_stored == pytest.approx(linear_to_ivne_volume_float(10 ** (-6 / 20)), rel=1e-5)


def test_logic_re_mute_fixture_if_present():
    base = Path("/tmp/daw2logic-re/mixer_baseline.logicx")
    muted = Path("/tmp/daw2logic-re/bass_muted.logicx")
    if not (base / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic mute baseline fixture")
    if not (muted / "Alternatives/000/ProjectData").is_file():
        pytest.skip("no local Logic mute capture")
    pd0 = ProjectData.parse((base / "Alternatives/000/ProjectData").read_bytes())
    pd1 = ProjectData.parse((muted / "Alternatives/000/ProjectData").read_bytes())
    ch = instrument_channels(pd0)[2]
    assert _ocua_for_channel(pd0, ch).raw[OCUA_MUTE_OFF] == 0
    assert _ocua_for_channel(pd1, ch).raw[OCUA_MUTE_OFF] == OCUA_MUTE_ON


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
