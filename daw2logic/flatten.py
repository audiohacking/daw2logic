"""Flatten nested DAWproject clip trees into timeline clips."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from .ir import AudioClip, MidiClip, Note, WarpPoint


def _float_attr(el: ET.Element, name: str, default: float = 0.0) -> float:
    raw = el.get(name)
    return float(raw) if raw is not None else default


def _optional_float(el: ET.Element, name: str) -> float | None:
    raw = el.get(name)
    return float(raw) if raw is not None else None


def _parse_warps(clip: ET.Element) -> AudioClip | None:
    warps_el = clip.find("Warps")
    if warps_el is None:
        return None
    audio = warps_el.find("Audio")
    if audio is None:
        return None
    file_el = audio.find("File")
    if file_el is None or not file_el.get("path"):
        return None
    rate_raw = audio.get("sampleRate")
    ch_raw = audio.get("channels")
    warp_pts = tuple(
        WarpPoint(time=_float_attr(w, "time"), content_time=_float_attr(w, "contentTime"))
        for w in warps_el.findall("Warp")
    )
    return AudioClip(
        start=0.0,
        duration=_float_attr(clip, "duration"),
        path=file_el.get("path"),
        name=clip.get("name"),
        sample_rate=int(float(rate_raw)) if rate_raw else None,
        channels=int(ch_raw) if ch_raw else None,
        play_start=_float_attr(clip, "playStart"),
        fade_in=_optional_float(clip, "fadeInTime"),
        fade_out=_optional_float(clip, "fadeOutTime"),
        fade_time_unit=clip.get("fadeTimeUnit"),
        warps=warp_pts,
        warp_time_unit=warps_el.get("timeUnit", "beats"),
        content_time_unit=warps_el.get("contentTimeUnit", "seconds"),
        algorithm=audio.get("algorithm"),
    )


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
                    release=float(n.get("rel")) if n.get("rel") else None,
                )
                for n in notes_el.findall("Note")
            )
            if notes:
                out.append(
                    MidiClip(
                        start=start,
                        duration=duration,
                        notes=notes,
                        name=clip.get("name"),
                        play_start=_float_attr(clip, "playStart"),
                        fade_in=_optional_float(clip, "fadeInTime"),
                        fade_out=_optional_float(clip, "fadeOutTime"),
                        fade_time_unit=clip.get("fadeTimeUnit"),
                    )
                )
        nested = clip.find("Clips")
        if nested is not None:
            out.extend(_collect_notes(nested, start))
    return out


def _collect_audio(clips_el: ET.Element, offset: float) -> list[AudioClip]:
    out: list[AudioClip] = []
    for clip in clips_el.findall("Clip"):
        start = offset + _float_attr(clip, "time")
        parsed = _parse_warps(clip)
        if parsed is not None:
            out.append(
                AudioClip(
                    start=start,
                    duration=parsed.duration or _float_attr(clip, "duration"),
                    path=parsed.path,
                    name=parsed.name or clip.get("name"),
                    sample_rate=parsed.sample_rate,
                    channels=parsed.channels,
                    play_start=parsed.play_start,
                    fade_in=parsed.fade_in,
                    fade_out=parsed.fade_out,
                    fade_time_unit=parsed.fade_time_unit,
                    warps=parsed.warps,
                    warp_time_unit=parsed.warp_time_unit,
                    content_time_unit=parsed.content_time_unit,
                    algorithm=parsed.algorithm,
                )
            )
        nested = clip.find("Clips")
        if nested is not None:
            for inner in _collect_audio(nested, start):
                out.append(inner)
    return out


def clips_from_lanes(
    lanes_el: ET.Element,
) -> tuple[tuple[MidiClip, ...], tuple[AudioClip, ...]]:
    """Extract MIDI and audio clips from a track's arrangement lane."""
    clips_el = lanes_el.find("Clips")
    if clips_el is None:
        return (), ()
    return tuple(_collect_notes(clips_el, 0.0)), tuple(_collect_audio(clips_el, 0.0))
