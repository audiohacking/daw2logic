"""Flatten nested DAWproject clip trees into timeline clips."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .ir import AudioClip, MidiClip, Note


def _float_attr(el: ET.Element, name: str, default: float = 0.0) -> float:
    raw = el.get(name)
    return float(raw) if raw is not None else default


def _collect_notes(clips_el: ET.Element, offset: float) -> list[MidiClip]:
    out: list[MidiClip] = []
    for clip in clips_el.findall("Clip"):
        start = offset + _float_attr(clip, "time")
        duration = _float_attr(clip, "duration")
        notes_el = clip.find("Notes")
        if notes_el is not None:
            notes = tuple(
                Note(
                    time=_float_attr(n, "time"),
                    duration=_float_attr(n, "duration"),
                    pitch=int(n.get("key", "60")),
                    velocity=float(n.get("vel", "1.0")),
                )
                for n in notes_el.findall("Note")
            )
            if notes:
                out.append(MidiClip(start=start, duration=duration, notes=notes))
        nested = clip.find("Clips")
        if nested is not None:
            out.extend(_collect_notes(nested, start))
    return out


def _first_audio(clip: ET.Element) -> tuple[str, int | None] | None:
    warps = clip.find("Warps")
    if warps is None:
        return None
    audio = warps.find("Audio")
    if audio is None:
        return None
    file_el = audio.find("File")
    if file_el is None or not file_el.get("path"):
        return None
    rate_raw = audio.get("sampleRate")
    rate = int(float(rate_raw)) if rate_raw else None
    return file_el.get("path"), rate


def _collect_audio(clips_el: ET.Element, offset: float) -> list[AudioClip]:
    out: list[AudioClip] = []
    for clip in clips_el.findall("Clip"):
        start = offset + _float_attr(clip, "time")
        duration = _float_attr(clip, "duration")
        audio_ref = _first_audio(clip)
        if audio_ref is not None:
            path, rate = audio_ref
            out.append(
                AudioClip(start=start, duration=duration, path=path, sample_rate=rate)
            )
        nested = clip.find("Clips")
        if nested is not None:
            out.extend(_collect_audio(nested, start))
    return out


def clips_from_lanes(lanes_el: ET.Element) -> tuple[tuple[MidiClip, ...], tuple[AudioClip, ...]]:
    """Extract MIDI and audio clips from a track's arrangement lane."""
    clips_el = lanes_el.find("Clips")
    if clips_el is None:
        return (), ()
    midi = _collect_notes(clips_el, 0.0)
    audio = _collect_audio(clips_el, 0.0)
    return tuple(midi), tuple(audio)
