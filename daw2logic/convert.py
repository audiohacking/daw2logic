"""Convert parsed DAWproject sessions to Logic Pro .logicx bundles."""

from __future__ import annotations

import plistlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from logicx.projectdata import ProjectData, synthesize_av_region_bundle

from . import parser
from .ir import Project
from .time import beats_to_note_tick, beats_to_tick, velocity_to_midi


@dataclass
class ConversionReport:
    warnings: list[str] = field(default_factory=list)
    instrument_tracks: int = 0
    audio_tracks: int = 0
    midi_regions: int = 0
    audio_regions: int = 0
    tempo: float = 120.0


def _resolve_audio(path: str, project: Project) -> Path:
    candidate = project.extract_dir / path
    if not candidate.is_file():
        raise FileNotFoundError(f"embedded audio not found: {path}")
    return candidate


def _apply_tempo(logicx_dir: Path, bpm: float) -> None:
    alt = logicx_dir / "Alternatives" / "000"
    pd_path = alt / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())
    pd.set_tempo(bpm)
    pd_path.write_bytes(pd.serialize())

    md_path = alt / "MetaData.plist"
    md = plistlib.loads(md_path.read_bytes())
    md["BeatsPerMinute"] = float(bpm)
    md_path.write_bytes(plistlib.dumps(md, fmt=plistlib.FMT_BINARY))


def convert(project: Project, out: Path) -> ConversionReport:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")

    inst_tracks = [t for t in project.tracks if t.midi_clips]
    aud_tracks = [t for t in project.tracks if t.audio_clips]

    report = ConversionReport(
        warnings=list(project.warnings),
        instrument_tracks=len(inst_tracks),
        audio_tracks=len(aud_tracks),
        tempo=project.transport.tempo,
    )

    if not inst_tracks and not aud_tracks:
        raise ValueError("project has no MIDI or audio clips to convert")

    midi_regions: list[tuple] = []
    for i, track in enumerate(inst_tracks, start=1):
        for clip in track.midi_clips:
            notes = tuple(
                (
                    beats_to_note_tick(n.time),
                    n.pitch,
                    velocity_to_midi(n.velocity),
                    beats_to_note_tick(n.duration),
                )
                for n in clip.notes
            )
            tick = beats_to_tick(clip.start)
            midi_regions.append((i, notes, tick, track.name))
            report.midi_regions += 1

    audio_regions: list[tuple] = []
    for i, track in enumerate(aud_tracks, start=1):
        for clip in track.audio_clips:
            wav = _resolve_audio(clip.path, project)
            tick = beats_to_tick(clip.start)
            audio_regions.append((i, wav, tick))
            report.audio_regions += 1
            if clip.duration > 0:
                report.warnings.append(
                    f"track '{track.name}': clip duration/warp not applied "
                    f"({clip.duration} beats); full file placed at tick {tick}"
                )

    instruments = len(inst_tracks)
    audio = len(aud_tracks)
    if instruments == 0:
        instruments = 0
    if audio == 0:
        audio = 0

    # mixed template requires at least one of each type when using defaults;
    # synthesize_av_region_bundle accepts instruments=0 or audio=0.
    summary = synthesize_av_region_bundle(
        None,
        out,
        instruments=instruments,
        audio=audio,
        inst_names=[t.name for t in inst_tracks] if inst_tracks else None,
        audio_names=[t.name for t in aud_tracks] if aud_tracks else None,
        midi_regions=midi_regions or None,
        audio_regions=audio_regions or None,
        verbose=False,
    )
    report.warnings.append(f"logicx synthesis: {summary}")

    bundle = out if out.suffix == ".logicx" else out
    if bundle.is_dir():
        _apply_tempo(bundle, project.transport.tempo)

    return report


def convert_file(dawproject: Path, out: Path) -> ConversionReport:
    project = parser.load(dawproject)
    try:
        return convert(project, out)
    finally:
        parser.cleanup(project)
