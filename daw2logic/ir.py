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


@dataclass(frozen=True)
class MidiClip:
    start: float
    duration: float
    notes: tuple[Note, ...]


@dataclass(frozen=True)
class AudioClip:
    start: float
    duration: float
    path: str
    sample_rate: int | None = None


@dataclass(frozen=True)
class Track:
    id: str
    name: str
    content_type: str
    role: str
    midi_clips: tuple[MidiClip, ...] = ()
    audio_clips: tuple[AudioClip, ...] = ()


@dataclass(frozen=True)
class Transport:
    tempo: float
    numerator: int
    denominator: int


@dataclass
class Project:
    transport: Transport
    tracks: list[Track]
    source: Path
    extract_dir: Path
    warnings: list[str] = field(default_factory=list)
