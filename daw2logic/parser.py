"""Load .dawproject ZIP archives into the internal representation."""

from __future__ import annotations

import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .flatten import clips_from_lanes
from .ir import Project, Track, Transport


def _channel_role(channel: ET.Element) -> str:
    return channel.get("role", "regular")


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

    tempo_el = root.find("./Transport/Tempo")
    sig_el = root.find("./Transport/TimeSignature")
    if tempo_el is None or sig_el is None:
        raise ValueError("project.xml missing Transport tempo or time signature")
    transport = Transport(
        tempo=float(tempo_el.get("value", "120")),
        numerator=int(sig_el.get("numerator", "4")),
        denominator=int(sig_el.get("denominator", "4")),
    )
    if transport.numerator != 4 or transport.denominator != 4:
        warnings.append(
            f"time signature {transport.numerator}/{transport.denominator} "
            "mapped with 4/4 tick math (meter maps not yet implemented)"
        )

    tracks_by_id: dict[str, ET.Element] = {}
    for track_el in root.findall("./Structure/Track"):
        tid = track_el.get("id")
        if tid:
            tracks_by_id[tid] = track_el

    lane_by_track: dict[str, ET.Element] = {}
    for lanes in root.findall("./Arrangement//Lanes"):
        track_ref = lanes.get("track")
        if track_ref and lanes.find("Clips") is not None:
            lane_by_track[track_ref] = lanes

    tracks: list[Track] = []
    for tid, track_el in tracks_by_id.items():
        channel = track_el.find("Channel")
        if channel is None:
            continue
        role = _channel_role(channel)
        if role == "master":
            continue

        content_type = track_el.get("contentType", "")
        lane = lane_by_track.get(tid)
        midi_clips: tuple = ()
        audio_clips: tuple = ()
        if lane is not None:
            midi_clips, audio_clips = clips_from_lanes(lane)

        if channel.find(".//ClapPlugin") is not None or channel.find(".//Vst3Plugin") is not None:
            warnings.append(f"track '{track_el.get('name', tid)}': plugin state not imported")
        if channel.find(".//AuPlugin") is not None:
            warnings.append(f"track '{track_el.get('name', tid)}': AU plugin state not imported")

        tracks.append(
            Track(
                id=tid,
                name=track_el.get("name", tid),
                content_type=content_type,
                role=role,
                midi_clips=midi_clips,
                audio_clips=audio_clips,
            )
        )

    return Project(
        transport=transport,
        tracks=tracks,
        source=path,
        extract_dir=extract_dir,
        warnings=warnings,
    )


def cleanup(project: Project) -> None:
    shutil.rmtree(project.extract_dir, ignore_errors=True)
