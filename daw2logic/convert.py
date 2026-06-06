"""Convert parsed DAWproject sessions to Logic Pro .logicx bundles."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass, field
from pathlib import Path

from logicx.projectdata import ProjectData, synthesize_av_region_bundle

from . import parser
from .audio import prepare_audio_clip
from .ir import Project
from .time import PPQ, beats_to_note_tick, beats_to_tick, build_time_map, velocity_to_midi
from .transport_logic import apply_transport


@dataclass
class ConversionReport:
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    instrument_tracks: int = 0
    audio_tracks: int = 0
    midi_regions: int = 0
    audio_regions: int = 0
    markers: int = 0
    tempo: float = 120.0
    title: str | None = None


def _resolve_audio(path: str, project: Project) -> Path:
    candidate = project.extract_dir / path
    if not candidate.is_file():
        raise FileNotFoundError(f"embedded audio not found: {path}")
    return candidate


def _patch_region_names(logicx_dir: Path, names: list[str]) -> None:
    """Set audio region display names when they differ from the wav stem."""
    if not names:
        return
    pd_path = logicx_dir / "Alternatives" / "000" / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())
    idx = 0
    for r in pd.records:
        if r.tag != b"gRuA":
            continue
        if idx >= len(names):
            break
        pd.patch_audio_region(idx, region_name=names[idx])
        idx += 1
    pd_path.write_bytes(pd.serialize())


def _apply_title(logicx_dir: Path, title: str | None) -> None:
    if not title:
        return
    info_path = logicx_dir / "Resources" / "ProjectInformation.plist"
    if not info_path.is_file():
        return
    info = plistlib.loads(info_path.read_bytes())
    variants = info.get("VariantNames") or {}
    if variants:
        first_key = sorted(variants.keys(), key=lambda k: int(k))[0]
        variants[first_key] = title
        info["VariantNames"] = variants
    info_path.write_bytes(plistlib.dumps(info, fmt=plistlib.FMT_BINARY))


def convert(project: Project, out: Path) -> ConversionReport:
    out = Path(out)
    if out.exists():
        raise FileExistsError(f"refusing to overwrite {out}")

    time_map = build_time_map(project.transport)
    inst_tracks = [t for t in project.tracks if t.midi_clips]
    aud_tracks = [t for t in project.tracks if t.audio_clips]

    report = ConversionReport(
        warnings=list(project.warnings),
        instrument_tracks=len(inst_tracks),
        audio_tracks=len(aud_tracks),
        markers=len(project.markers),
        tempo=project.transport.tempo,
        title=project.metadata.title,
    )

    if not inst_tracks and not aud_tracks:
        raise ValueError("project has no MIDI or audio clips to convert")

    work_dir = project.extract_dir / "prepared"
    work_dir.mkdir(exist_ok=True)

    midi_regions: list[tuple] = []
    for i, track in enumerate(inst_tracks, start=1):
        for clip in track.midi_clips:
            notes = tuple(
                (
                    beats_to_note_tick(n.time - clip.play_start),
                    n.pitch,
                    velocity_to_midi(n.velocity),
                    beats_to_note_tick(n.duration),
                )
                for n in clip.notes
            )
            tick = beats_to_tick(clip.start, time_map)
            region_name = clip.name or track.name
            midi_regions.append((i, notes, tick, region_name))
            report.midi_regions += 1
            if clip.fade_in or clip.fade_out:
                report.warnings.append(
                    f"track '{track.name}': MIDI clip fades not imported"
                )

    audio_regions: list[tuple] = []
    audio_names: list[str] = []
    for i, track in enumerate(aud_tracks, start=1):
        for clip in track.audio_clips:
            source = _resolve_audio(clip.path, project)
            prepared, awarn = prepare_audio_clip(clip, source, work_dir, project.transport)
            report.warnings.extend(awarn)
            tick = beats_to_tick(clip.start, time_map)
            audio_regions.append((i, prepared, tick))
            audio_names.append(clip.name or track.name)
            report.audio_regions += 1

    synthesize_av_region_bundle(
        None,
        out,
        instruments=len(inst_tracks),
        audio=len(aud_tracks),
        inst_names=[t.name for t in inst_tracks] if inst_tracks else None,
        audio_names=[t.name for t in aud_tracks] if aud_tracks else None,
        midi_regions=midi_regions or None,
        audio_regions=audio_regions or None,
        verbose=False,
    )

    bundle = out
    if bundle.is_dir():
        report.warnings.extend(apply_transport(bundle, project.transport, project.markers))
        _patch_region_names(bundle, audio_names)
        _apply_title(bundle, project.metadata.title)

    for track in project.tracks:
        if track.color:
            report.skipped.append(f"track color '{track.name}': {track.color}")

    return report


def convert_file(dawproject: Path, out: Path) -> ConversionReport:
    project = parser.load(dawproject)
    try:
        return convert(project, out)
    finally:
        parser.cleanup(project)
