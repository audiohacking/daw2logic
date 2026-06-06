"""End-to-end conversion tests."""

from __future__ import annotations

import json
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


def test_convert_processes_stretched_audio(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    region_frames = _audio_region_frames(logicx_output)[0]
    src = Path("third_party/dawproject/test-data/white-glasses.wav")
    with wave.open(str(src), "rb") as wf:
        source_frames = wf.getnframes()
    assert region_frames < source_frames


def test_convert_keeps_full_source_without_stretch(tmp_path):
    import zipfile

    wav_path = Path("third_party/dawproject/test-data/white-glasses.wav")
    if not wav_path.is_file():
        pytest.skip("dawproject submodule wav missing")

    project_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Project version="1.0">
  <Transport>
    <Tempo unit="bpm" value="120.000000" id="id0" name="Tempo"/>
    <TimeSignature denominator="4" numerator="4" id="id1"/>
  </Transport>
  <Structure>
    <Track contentType="audio" loaded="true" id="id2" name="Drums">
      <Channel audioChannels="2" destination="id4" role="regular" id="id3"/>
    </Track>
    <Track contentType="audio notes" loaded="true" id="id5" name="Master">
      <Channel audioChannels="2" role="master" id="id4"/>
    </Track>
  </Structure>
  <Arrangement>
    <Lanes timeUnit="beats">
      <Lanes track="id2">
        <Clips>
          <Clip time="0.0" duration="4.0" playStart="0.0" name="Loop">
            <Warps contentTimeUnit="seconds" timeUnit="beats">
              <Audio algorithm="none" channels="2" sampleRate="48000">
                <File path="audio/white-glasses.wav"/>
              </Audio>
              <Warp time="0.0" contentTime="0.0"/>
              <Warp time="4.0" contentTime="4.0"/>
            </Warps>
          </Clip>
        </Clips>
      </Lanes>
    </Lanes>
  </Arrangement>
</Project>"""
    metadata = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<MetaData><Title>Plain audio</Title></MetaData>"""
    daw = tmp_path / "plain.dawproject"
    with zipfile.ZipFile(daw, "w") as zf:
        zf.writestr("metadata.xml", metadata)
        zf.writestr("project.xml", project_xml)
        zf.write(wav_path, "audio/white-glasses.wav")

    out = tmp_path / "out.logicx"
    report = convert_file(daw, out)
    with wave.open(str(wav_path), "rb") as wf:
        source_frames = wf.getnframes()
    assert _audio_region_frames(out)[0] == source_frames
    assert not any("time-stretch" in w for w in report.warnings)


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


def test_convert_exports_mixer_manifest(bitwig_simple_dawproject, logicx_output):
    report = convert_file(bitwig_simple_dawproject, logicx_output)
    assert "Bass" in report.mixer_patched_tracks
    assert "Drumloop" in report.mixer_patched_tracks
    manifest = json.loads(
        (logicx_output / "Media/daw2logic Import/manifest.json").read_text()
    )
    bass = next(t for t in manifest["tracks"] if t["name"] == "Bass")
    assert bass["mixer"]["volume_linear"] == pytest.approx(0.659140)


def test_convert_refuses_overwrite(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    with pytest.raises(FileExistsError):
        convert_file(bitwig_simple_dawproject, logicx_output)


def test_convert_force_overwrite(bitwig_simple_dawproject, logicx_output):
    convert_file(bitwig_simple_dawproject, logicx_output)
    report = convert_file(bitwig_simple_dawproject, logicx_output, force=True)
    assert report.audio_regions >= 1
