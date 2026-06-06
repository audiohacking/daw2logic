"""End-to-end conversion tests."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from daw2logic.convert import convert_file
from logicx.projectdata import ProjectData


def _read_tempo(logicx: Path) -> float:
    md = plistlib.loads((logicx / "Alternatives" / "000" / "MetaData.plist").read_bytes())
    return float(md["BeatsPerMinute"])


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


def test_convert_sets_tempo_in_metadata(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    assert _read_tempo(logicx_output) == pytest.approx(149.0)


def test_convert_projectdata_parses(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    data = (logicx_output / "Alternatives" / "000" / "ProjectData").read_bytes()
    pd = ProjectData.parse(data)
    assert len(pd.records) > 0
    assert pd.serialize() == data


def test_convert_refuses_overwrite(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    with pytest.raises(FileExistsError):
        convert_file(bitwig_simple_dawproject, logicx_output)
