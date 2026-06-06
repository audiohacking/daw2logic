"""Intermediate representation for a DAWproject session."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Note:
    time: float
    duration: float
    pitch: int
    velocity: float
    release: float | None = None


@dataclass(frozen=True)
class WarpPoint:
    time: float
    content_time: float


@dataclass(frozen=True)
class MidiClip:
    start: float
    duration: float
    notes: tuple[Note, ...]
    name: str | None = None
    play_start: float = 0.0
    fade_in: float | None = None
    fade_out: float | None = None
    fade_time_unit: str | None = None


@dataclass(frozen=True)
class AudioClip:
    start: float
    duration: float
    path: str
    name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    play_start: float = 0.0
    fade_in: float | None = None
    fade_out: float | None = None
    fade_time_unit: str | None = None
    warps: tuple[WarpPoint, ...] = ()
    warp_time_unit: str = "beats"
    content_time_unit: str = "seconds"
    algorithm: str | None = None


@dataclass(frozen=True)
class PluginInfo:
    kind: str
    name: str | None
    device_id: str | None
    state_path: str | None


@dataclass(frozen=True)
class Track:
    id: str
    name: str
    content_type: str
    role: str
    color: str | None = None
    volume: float | None = None
    pan: float | None = None
    mute: bool | None = None
    solo: bool | None = None
    plugins: tuple[PluginInfo, ...] = ()
    midi_clips: tuple[MidiClip, ...] = ()
    audio_clips: tuple[AudioClip, ...] = ()


@dataclass(frozen=True)
class TempoPoint:
    time: float
    bpm: float


@dataclass(frozen=True)
class MeterPoint:
    time: float
    numerator: int
    denominator: int


@dataclass(frozen=True)
class Marker:
    time: float
    name: str


@dataclass(frozen=True)
class Transport:
    tempo: float
    numerator: int
    denominator: int
    tempo_map: tuple[TempoPoint, ...] = ()
    meter_map: tuple[MeterPoint, ...] = ()


@dataclass(frozen=True)
class Metadata:
    title: str | None = None
    artist: str | None = None
    comment: str | None = None


@dataclass
class Project:
    transport: Transport
    metadata: Metadata
    tracks: list[Track]
    markers: tuple[Marker, ...]
    source: Path
    extract_dir: Path
    warnings: list[str] = field(default_factory=list)
