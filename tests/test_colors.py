"""Color parsing and Logic ProjectData patching tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import struct

from daw2logic.colors import nearest_logic_picker_index, parse_hex_color, qesm_track_color_bytes, region_color_bytes
from daw2logic.colors_logic import (
    GRUA_COLOR_BLOB_OFF,
    GRUA_COLOR_FLAG_OFF,
    QESM_COLOR_AUX_OFF,
    QESM_COLOR_U32_OFF,
    patch_grua_region_color,
    patch_qesm_track_color,
)
from daw2logic.convert import convert_file
from daw2logic.flatten import clips_from_lanes
from daw2logic.logicx_channels import audio_channels
from daw2logic.parser import cleanup, load
from logicx.projectdata import ProjectData
import xml.etree.ElementTree as ET


def test_parse_hex_color():
    assert parse_hex_color("#5761c6") == (0x57, 0x61, 0xC6)


def test_qesm_track_color_matches_capture():
    u32, aux = qesm_track_color_bytes(4, 0x640000)
    assert u32 == 0x000004CE
    assert aux == 0xA4
    u32, aux = qesm_track_color_bytes(6, 0x600000)
    assert u32 == 0x0000066D
    assert aux == 0xA0


def test_patch_qesm_and_grua():
    raw = bytes(345)
    out = patch_qesm_track_color(raw, picker_index=4, channel=0x640000)
    assert struct.unpack_from("<I", out, QESM_COLOR_U32_OFF)[0] == 0x000004CE
    assert out[QESM_COLOR_AUX_OFF] == 0xA4

    grua = bytearray(246)
    grua[0x27] = 0x20
    out_g = patch_grua_region_color(bytes(grua), hex_color="#009d47")
    assert out_g[GRUA_COLOR_FLAG_OFF] == 0x10
    assert out_g[GRUA_COLOR_BLOB_OFF : GRUA_COLOR_BLOB_OFF + 8] == region_color_bytes("#009d47")


def test_flatten_reads_clip_color():
    xml = """<Lanes track="t1">
      <Clips>
        <Clip time="0.0" duration="4.0" color="#009d47">
          <Clips>
            <Clip time="0.0" duration="4.0" playStart="0.0">
              <Warps contentTimeUnit="seconds" timeUnit="beats">
                <Audio algorithm="stretch" channels="2" sampleRate="48000">
                  <File path="audio/x.wav"/>
                </Audio>
                <Warp time="0.0" contentTime="0.0"/>
                <Warp time="4.0" contentTime="2.0"/>
              </Warps>
            </Clip>
          </Clips>
        </Clip>
      </Clips>
    </Lanes>"""
    _, audio = clips_from_lanes(ET.fromstring(xml))
    assert audio[0].color == "#009d47"


def test_grease1_convert_preserves_template_qesm_colors(tmp_path):
    grease = Path("tmp/GREASE1.dawproject")
    if not grease.is_file():
        pytest.skip("local GREASE1 fixture not present")
    out = tmp_path / "out.logicx"
    report = convert_file(grease, out)
    assert not report.color_patched_tracks
    pd = ProjectData.parse((out / "Alternatives/000/ProjectData").read_bytes())
    drum_ch = audio_channels(pd)[1]  # 2 Drums is first exported audio track
    qesm = next(
        r for r in pd.records
        if r.tag == b"qeSM" and struct.unpack_from("<I", r.raw, 0x08)[0] == drum_ch
    )
    u32 = struct.unpack_from("<I", qesm.raw, QESM_COLOR_U32_OFF)[0]
    assert u32 == 0x000004B1  # template Audio 1 default (unchanged by disabled color graft)


def test_grease1_parses_colors():
    grease = Path("tmp/GREASE1.dawproject")
    if not grease.is_file():
        pytest.skip("local GREASE1 fixture not present")
    project = load(grease)
    try:
        drums = next(t for t in project.tracks if t.name == "2 Drums")
        assert drums.color == "#5761c6"
        assert any(c.color == "#009d47" for c in drums.audio_clips)
        assert nearest_logic_picker_index("#5761c6") == 29
    finally:
        cleanup(project)
