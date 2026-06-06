"""End-to-end conversion tests."""

from __future__ import annotations

import plistlib
import struct
import wave
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from daw2logic.parser import cleanup, load
from logicx.projectdata import ProjectData


def _read_tempo(logicx: Path) -> float:
    md = plistlib.loads((logicx / "Alternatives" / "000" / "MetaData.plist").read_bytes())
    return float(md["BeatsPerMinute"])


def _audio_region_frames(logicx: Path) -> list[int]:
    pd = ProjectData.parse((logicx / "Alternatives" / "000" / "ProjectData").read_bytes())
    frames = []
    for r in pd.records:
        if r.tag == b"gRuA":
            frames.append(struct.unpack_from("<I", r.raw, 0x24 + ProjectData.GRUA_SAMPLELEN_OFF)[0])
    return frames


def test_convert_bitwig_simple_produces_logicx_bundle(
    bitwig_simple_dawproject, logicx_output
):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    assert logicx_output.is_dir()
    assert (logicx_output / "Alternatives" / "000" / "ProjectData").is_file()
    assert report.instrument_tracks == 1
    assert report.audio_tracks == 1
    assert report.midi_regions == 1
    assert report.audio_regions == 1
    assert report.tempo == 149.0
    assert not any("clip duration/warp not applied" in w for w in report.warnings)


def test_convert_trims_audio_region(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    region_frames = _audio_region_frames(logicx_output)[0]
    src = Path("third_party/dawproject/test-data/white-glasses.wav")
    with wave.open(str(src), "rb") as wf:
        source_frames = wf.getnframes()
    assert region_frames < source_frames


def test_convert_sets_tempo_in_metadata(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    assert _read_tempo(logicx_output) == pytest.approx(149.0)


def test_convert_projectdata_parses(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    data = (logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes()
    pd = ProjectData.parse(data)
    assert len(pd.records) > 0
    assert pd.serialize() == data


def test_convert_extended_tempo_map_and_markers(
    bitwig_extended_dawproject, logicx_output
):
    report = convert_file(bitwig_extended_dawproject, logicx_output)
    assert report.markers == 2
    pd = ProjectData.parse((logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes())
    tempo_map = pd.get_tempo_map()
    assert len(tempo_map) >= 2
    assert tempo_map[0][1] == pytest.approx(120.0)
    assert tempo_map[1][1] == pytest.approx(140.0)


def test_convert_reports_mixer_and_plugins(bitwig_simple_dawproject):
    project = load(bitwig_simple_dawproject)
    try:
        warnings = project.warnings
        assert any("mixer settings" in w for w in warnings)
    finally:
        cleanup(project)


def test_convert_refuses_overwrite(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    with pytest.raises(FileExistsError):
        convert_file(bitwig_simple_dawproject, logicx_output)
