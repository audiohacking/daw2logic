"""Tests for track ordinal mapping and arrange reorder."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.parser import cleanup, load
from daw2logic.track_order import is_interleaved
from logicx.projectdata import IVNE_NAME, IVNE_NAME_LEN, KART_CHAN, ProjectData, _u32


def _arrange_names(logicx: Path) -> list[str]:
    pd = ProjectData.parse((logicx / "Alternatives" / "000" / "ProjectData").read_bytes())
    names: list[str] = []
    for r in pd.records:
        if r.tag != b"karT" or len(r.raw) != 93 or _u32(r.raw, 0x08) != 0x040000:
            continue
        if _u32(r.raw, KART_CHAN) == 0x500000:
            continue
        ch = _u32(r.raw, KART_CHAN)
        iv = next(x for x in pd.records if x.tag == b"ivnE" and _u32(x.raw, 0x08) == ch)
        nlen = struct.unpack_from("<H", iv.raw, IVNE_NAME_LEN)[0]
        names.append(iv.raw[IVNE_NAME : IVNE_NAME + nlen].decode("latin-1", "replace"))
    return names


def _placement_tracks(logicx: Path) -> dict[str, int]:
    pd = ProjectData.parse((logicx / "Alternatives" / "000" / "ProjectData").read_bytes())
    aq = ProjectData._arrange_audio_evsq(pd.records)
    assert aq is not None
    raw = pd.records[aq].raw
    body = raw[24 : 24 + struct.unpack_from("<I", raw, 0x1C)[0]]
    out: dict[str, int] = {}
    o = 0
    while o + 0x50 <= len(body):
        tag = struct.unpack_from("<I", body, o)[0]
        if tag == 0x20:
            out["midi"] = body[o + 0x14]
        elif tag == 0x24:
            out["audio"] = body[o + 0x14]
        o += 4
    return out


def test_regions_target_synthesized_tracks(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    names = _arrange_names(logicx_output)
    assert "Inst 1" not in names
    assert "Audio 1" not in names
    assert "Bass" in names
    assert "Drumloop" in names
    placements = _placement_tracks(logicx_output)
    bass_pos = names.index("Bass") + 1
    drum_pos = names.index("Drumloop") + 1
    assert placements["midi"] == bass_pos
    assert placements["audio"] == drum_pos


@pytest.fixture(scope="session")
def bitwig_interleaved_dawproject() -> Path:
    path = Path("tests/fixtures/bitwig_interleaved.dawproject")
    if not path.is_file():
        import subprocess
        import sys

        subprocess.run([sys.executable, "tests/fixtures/build_bitwig_simple.py"], check=True)
    assert path.is_file()
    return path


def test_interleaved_fixture_order(bitwig_interleaved_dawproject):
    project = load(bitwig_interleaved_dawproject)
    try:
        assert is_interleaved(project)
        exported = [t.name for t in project.tracks if t.midi_clips or t.audio_clips]
        assert exported[0] == "Drumloop"
        assert exported[1] == "Bass"
    finally:
        cleanup(project)


def test_interleaved_arrange_reorder(bitwig_interleaved_dawproject, logicx_output):
    report = convert_file(bitwig_interleaved_dawproject, logicx_output)
    assert any("reordered Logic arrange tracks" in w for w in report.warnings)
    names = _arrange_names(logicx_output)
    drum_pos = names.index("Drumloop") + 1
    bass_pos = names.index("Bass") + 1
    assert drum_pos < bass_pos
    placements = _placement_tracks(logicx_output)
    assert placements["audio"] == drum_pos
    assert placements["midi"] == bass_pos
