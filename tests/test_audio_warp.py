"""Audio warp slicing and nested clip flatten tests."""

from __future__ import annotations

import struct
import wave

import pytest

from daw2logic.audio import content_range_seconds, prepare_audio_clip
from daw2logic.flatten import clips_from_lanes
from daw2logic.ir import AudioClip, Transport, WarpPoint
import xml.etree.ElementTree as ET


def test_content_range_interpolates_play_start():
    warps = (
        WarpPoint(0.0, 0.0),
        WarpPoint(371.7612085342407, 185.88060416666667),
    )
    clip = AudioClip(
        start=16.0,
        duration=2.0,
        path="audio/drums.wav",
        play_start=8.0,
        warps=warps,
        algorithm="stretch_subbands",
    )
    c0, c1 = content_range_seconds(clip)
    assert c0 == pytest.approx(4.0, abs=0.01)
    assert c1 == pytest.approx(5.0, abs=0.01)


def test_flatten_uses_parent_bounds_for_full_span_reference():
    xml = """<Lanes track="t1">
      <Clips>
        <Clip time="16.0" duration="1.0" playStart="76.0">
          <Clips>
            <Clip time="0.0" duration="371.7612085342407" playStart="0.0">
              <Warps contentTimeUnit="seconds" timeUnit="beats">
                <Audio algorithm="stretch_subbands" channels="2" sampleRate="48000">
                  <File path="audio/bass.wav"/>
                </Audio>
                <Warp time="0.0" contentTime="0.0"/>
                <Warp time="371.7612085342407" contentTime="185.88060416666667"/>
              </Warps>
            </Clip>
          </Clips>
        </Clip>
      </Clips>
    </Lanes>"""
    _, audio = clips_from_lanes(ET.fromstring(xml))
    assert len(audio) == 1
    assert audio[0].start == pytest.approx(16.0)
    assert audio[0].duration == pytest.approx(1.0)
    assert audio[0].play_start == pytest.approx(76.0)


def test_flatten_keeps_short_leaf_slices():
    xml = """<Lanes track="t1">
      <Clips>
        <Clip time="16.0" duration="8.0" playStart="0.0">
          <Clips>
            <Clip time="0.0" duration="2.0" playStart="8.0">
              <Warps contentTimeUnit="seconds" timeUnit="beats">
                <Audio algorithm="stretch_subbands" channels="2" sampleRate="48000">
                  <File path="audio/drums.wav"/>
                </Audio>
                <Warp time="0.0" contentTime="0.0"/>
                <Warp time="371.7612085342407" contentTime="185.88060416666667"/>
              </Warps>
            </Clip>
          </Clips>
        </Clip>
      </Clips>
    </Lanes>"""
    _, audio = clips_from_lanes(ET.fromstring(xml))
    assert len(audio) == 1
    assert audio[0].start == pytest.approx(16.0)
    assert audio[0].duration == pytest.approx(2.0)
    assert audio[0].play_start == pytest.approx(8.0)


def test_prepare_audio_clip_slices_seconds_not_whole_file(tmp_path):
    src = tmp_path / "tone.wav"
    rate = 48000
    frames = b"\x00\x00" * rate  # 1 second silence
    with wave.open(str(src), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(frames * 10)

    clip = AudioClip(
        start=0.0,
        duration=2.0,
        path="tone.wav",
        play_start=4.0,
        warps=(WarpPoint(0.0, 0.0), WarpPoint(8.0, 8.0)),
        algorithm="none",
    )
    transport = Transport(tempo=120.0, numerator=4, denominator=4)
    out, warnings = prepare_audio_clip(clip, src, tmp_path / "out", transport)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnframes() == pytest.approx(rate, rel=0.02)
    assert not any("8922275" in w for w in warnings)
