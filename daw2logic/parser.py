"""Load .dawproject ZIP archives into the internal representation."""

from __future__ import annotations

import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .flatten import clips_from_lanes
from .ir import (
    Marker,
    Metadata,
    MeterPoint,
    PluginInfo,
    Project,
    TempoPoint,
    Track,
    Transport,
)

_PLUGIN_TAGS = {
    "AuPlugin": "au",
    "Vst3Plugin": "vst3",
    "Vst2Plugin": "vst2",
    "ClapPlugin": "clap",
    "BuiltinDevice": "builtin",
}


def _float_attr(el: ET.Element | None, name: str, default: float | None = None) -> float | None:
    if el is None:
        return default
    raw = el.get(name)
    if raw is None:
        return default
    return float(raw)


def _bool_param(channel: ET.Element, tag: str) -> bool | None:
    el = channel.find(tag)
    if el is None:
        return None
    raw = el.get("value")
    if raw is None:
        return None
    return raw.lower() in {"true", "1"}


def _real_param(channel: ET.Element, tag: str) -> float | None:
    el = channel.find(tag)
    return _float_attr(el, "value")


def _parse_plugins(channel: ET.Element) -> tuple[PluginInfo, ...]:
    plugins: list[PluginInfo] = []
    devices = channel.find("Devices")
    if devices is None:
        return ()
    for tag, kind in _PLUGIN_TAGS.items():
        for el in devices.findall(tag):
            state = el.find("State")
            plugins.append(
                PluginInfo(
                    kind=kind,
                    name=el.get("deviceName") or el.get("name"),
                    device_id=el.get("deviceID"),
                    state_path=state.get("path") if state is not None else None,
                )
            )
    return tuple(plugins)


def _parse_tempo_map(root: ET.Element, default_bpm: float) -> tuple[TempoPoint, ...]:
    points: list[TempoPoint] = []
    auto = root.find("./Arrangement/TempoAutomation")
    if auto is not None:
        for pt in auto.findall("RealPoint"):
            points.append(TempoPoint(time=_float_attr(pt, "time", 0.0), bpm=_float_attr(pt, "value", default_bpm)))
    if not points:
        tempo_el = root.find("./Transport/Tempo")
        if tempo_el is not None:
            for pt in tempo_el.findall(".//RealPoint"):
                points.append(
                    TempoPoint(time=_float_attr(pt, "time", 0.0), bpm=_float_attr(pt, "value", default_bpm))
                )
    if not points:
        points.append(TempoPoint(0.0, default_bpm))
    return tuple(sorted(points, key=lambda p: p.time))


def _parse_meter_map(root: ET.Element, num: int, den: int) -> tuple[MeterPoint, ...]:
    points: list[MeterPoint] = []
    auto = root.find("./Arrangement/TimeSignatureAutomation")
    if auto is not None:
        for pt in auto.findall("TimeSignaturePoint"):
            points.append(
                MeterPoint(
                    time=_float_attr(pt, "time", 0.0),
                    numerator=int(pt.get("numerator", str(num))),
                    denominator=int(pt.get("denominator", str(den))),
                )
            )
    if not points:
        points.append(MeterPoint(0.0, num, den))
    return tuple(sorted(points, key=lambda p: p.time))


def _parse_markers(root: ET.Element) -> tuple[Marker, ...]:
    markers_el = root.find("./Arrangement/Markers")
    if markers_el is None:
        return ()
    out: list[Marker] = []
    for m in markers_el.findall("Marker"):
        name = m.get("name") or m.findtext("Name") or "Marker"
        out.append(Marker(time=_float_attr(m, "time", 0.0), name=name))
    return tuple(sorted(out, key=lambda m: m.time))


def _load_metadata(extract_dir: Path) -> Metadata:
    path = extract_dir / "metadata.xml"
    if not path.is_file():
        return Metadata()
    meta_root = ET.parse(path).getroot()
    return Metadata(
        title=_text(meta_root, "Title"),
        artist=_text(meta_root, "Artist"),
        comment=_text(meta_root, "Comment"),
    )


def _text(root: ET.Element, tag: str) -> str | None:
    el = root.find(tag)
    if el is None or not (el.text and el.text.strip()):
        return None
    return el.text.strip()


def _channel_role(channel: ET.Element) -> str:
    return channel.get("role", "regular")


def _warn_plugins(track_name: str, plugins: tuple[PluginInfo, ...]) -> list[str]:
    warnings: list[str] = []
    for plugin in plugins:
        if plugin.kind == "au" and plugin.state_path:
            warnings.append(
                f"track '{track_name}': AU preset at {plugin.state_path} not embedded "
                f"({plugin.name or 'AU plugin'})"
            )
        else:
            warnings.append(
                f"track '{track_name}': {plugin.kind.upper()} plugin "
                f"'{plugin.name or plugin.device_id or '?'}' not supported in Logic"
            )
    return warnings


def load(path: Path) -> Project:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    extract_dir = Path(tempfile.mkdtemp(prefix="daw2logic-"))
    warnings: list[str] = []

    with zipfile.ZipFile(path) as zf:
        if "project.xml" not in zf.namelist():
            raise ValueError("missing project.xml in .dawproject archive")
        zf.extractall(extract_dir)

    root = ET.parse(extract_dir / "project.xml").getroot()
    metadata = _load_metadata(extract_dir)

    tempo_el = root.find("./Transport/Tempo")
    sig_el = root.find("./Transport/TimeSignature")
    if tempo_el is None or sig_el is None:
        raise ValueError("project.xml missing Transport tempo or time signature")

    default_bpm = float(tempo_el.get("value", "120"))
    numerator = int(sig_el.get("numerator", "4"))
    denominator = int(sig_el.get("denominator", "4"))
    tempo_map = _parse_tempo_map(root, default_bpm)
    meter_map = _parse_meter_map(root, numerator, denominator)
    markers = _parse_markers(root)

    transport = Transport(
        tempo=default_bpm,
        numerator=numerator,
        denominator=denominator,
        tempo_map=tempo_map,
        meter_map=meter_map,
    )

    tracks_by_id: dict[str, ET.Element] = {}
    track_order: list[str] = []
    for track_el in root.findall("./Structure/Track"):
        tid = track_el.get("id")
        if tid:
            tracks_by_id[tid] = track_el
            track_order.append(tid)

    lane_by_track: dict[str, ET.Element] = {}
    for lanes in root.findall("./Arrangement//Lanes"):
        track_ref = lanes.get("track")
        if track_ref and lanes.find("Clips") is not None:
            lane_by_track[track_ref] = lanes

    if root.find("./Scenes/Scene") is not None or root.findall("./Scenes/*"):
        scenes = root.find("./Scenes")
        if scenes is not None and len(scenes):
            warnings.append("clip launcher scenes not imported")

    tracks: list[Track] = []
    for tid in track_order:
        track_el = tracks_by_id[tid]
        channel = track_el.find("Channel")
        if channel is None:
            continue
        role = _channel_role(channel)
        if role == "master":
            continue

        lane = lane_by_track.get(tid)
        midi_clips: tuple = ()
        audio_clips: tuple = ()
        if lane is not None:
            midi_clips, audio_clips = clips_from_lanes(lane)
            if lane.find(".//Points") is not None:
                warnings.append(
                    f"track '{track_el.get('name', tid)}': track automation not imported"
                )

        plugins = _parse_plugins(channel)
        warnings.extend(_warn_plugins(track_el.get("name", tid), plugins))

        vol, pan = _real_param(channel, "Volume"), _real_param(channel, "Pan")
        if vol is not None or pan is not None or _bool_param(channel, "Mute") is not None:
            warnings.append(
                f"track '{track_el.get('name', tid)}': mixer settings "
                "(volume/pan/mute) not imported"
            )

        tracks.append(
            Track(
                id=tid,
                name=track_el.get("name", tid),
                content_type=track_el.get("contentType", ""),
                role=role,
                color=track_el.get("color"),
                volume=vol,
                pan=pan,
                mute=_bool_param(channel, "Mute"),
                solo=channel.get("solo", "").lower() == "true",
                plugins=plugins,
                midi_clips=midi_clips,
                audio_clips=audio_clips,
            )
        )

    types = [("notes" in t.content_type or t.midi_clips, "audio" in t.content_type or t.audio_clips) for t in tracks]
    if any(a and b for a, b in types):
        inst_seen = aud_seen = False
        for has_midi, has_audio in types:
            if has_midi and aud_seen:
                warnings.append(
                    "interleaved instrument/audio track order may not match source "
                    "(Logic groups instruments then audio)"
                )
                break
            if has_midi:
                inst_seen = True
            if has_audio:
                aud_seen = True

    return Project(
        transport=transport,
        metadata=metadata,
        tracks=tracks,
        markers=markers,
        source=path,
        extract_dir=extract_dir,
        warnings=warnings,
    )


def cleanup(project: Project) -> None:
    shutil.rmtree(project.extract_dir, ignore_errors=True)
