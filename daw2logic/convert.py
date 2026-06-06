"""Convert parsed DAWproject sessions to Logic Pro .logicx bundles."""

from __future__ import annotations

import plistlib
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from logicx.projectdata import ProjectData, synthesize_av_region_bundle

from . import parser
from .audio import resolve_audio_clip
from .ir import Project
from .time import PPQ, beats_to_note_tick, beats_to_tick, build_time_map, velocity_to_midi
from .mixer_logic import apply_mixer
from .plugins import export_sidecars
from .track_order import (
    MIXED_TEMPLATE_AUDIO,
    MIXED_TEMPLATE_INSTRUMENTS,
    apply_template_track_names,
    apply_track_order,
    logic_aud_ordinal,
    logic_inst_ordinal,
    synth_audio_count,
    synth_instrument_count,
)
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
    plugins_copied: int = 0
    tempo: float = 120.0
    title: str | None = None
    mixer_patched_tracks: set[str] = field(default_factory=set)
    color_patched_tracks: set[str] = field(default_factory=set)


def conversion_notes_path(output: Path) -> Path:
    """Sibling .txt path for conversion notes (out.logicx → out.txt)."""
    output = Path(output)
    return output.with_suffix(".txt") if output.suffix else output.with_name(f"{output.name}.txt")


def _summarize_messages(messages: list[str]) -> list[str]:
    if not messages:
        return []
    lines: list[str] = []
    for message, count in Counter(messages).most_common():
        prefix = f"({count}x) " if count > 1 else ""
        lines.append(f"{prefix}{message}")
    return lines


def format_conversion_notes(
    report: ConversionReport,
    *,
    source: Path,
    output: Path,
) -> str:
    lines = [
        "daw2logic conversion notes",
        "==========================",
        f"Source: {source}",
        f"Output: {output}",
    ]
    if report.title:
        lines.append(f"Title: {report.title}")
    lines.extend(
        [
            f"Tempo: {report.tempo} BPM",
            "",
            "Summary",
            "-------",
            f"{report.instrument_tracks} instrument track(s)",
            f"{report.audio_tracks} audio track(s)",
            f"{report.midi_regions} MIDI region(s)",
            f"{report.audio_regions} audio region(s)",
            f"{report.markers} marker(s)",
            f"{report.plugins_copied} AU preset(s) copied to sidecar",
        ]
    )
    if report.mixer_patched_tracks:
        lines.extend(["", "Mixer patched", "-------------"])
        lines.extend(f"  {name}" for name in sorted(report.mixer_patched_tracks))
    if report.color_patched_tracks:
        lines.extend(["", "Colors patched", "--------------"])
        lines.extend(f"  {name}" for name in sorted(report.color_patched_tracks))
    if report.warnings:
        lines.extend(["", f"Warnings ({len(report.warnings)})", "--------"])
        lines.extend(f"  {line}" for line in _summarize_messages(report.warnings))
    if report.skipped:
        lines.extend(["", f"Manual / skipped ({len(report.skipped)})", "----------------"])
        lines.extend(f"  {line}" for line in _summarize_messages(report.skipped))
    return "\n".join(lines) + "\n"


def write_conversion_notes(
    report: ConversionReport,
    *,
    source: Path,
    output: Path,
    notes_path: Path | None = None,
) -> Path:
    path = Path(notes_path) if notes_path is not None else conversion_notes_path(output)
    path.write_text(format_conversion_notes(report, source=source, output=output))
    return path


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


def convert(project: Project, out: Path, *, force: bool = False) -> ConversionReport:
    out = Path(out)
    if out.exists():
        if not force:
            raise FileExistsError(f"refusing to overwrite {out}")
        if out.is_dir():
            shutil.rmtree(out)
        else:
            out.unlink()

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
            midi_regions.append((logic_inst_ordinal(i), notes, tick, region_name))
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
            prepared, awarn = resolve_audio_clip(clip, source, work_dir, project.transport)
            report.warnings.extend(awarn)
            tick = beats_to_tick(clip.start, time_map)
            audio_regions.append((logic_aud_ordinal(i), prepared, tick))
            audio_names.append(clip.name or track.name)
            report.audio_regions += 1

    synthesize_av_region_bundle(
        None,
        out,
        instruments=synth_instrument_count(len(inst_tracks)),
        audio=synth_audio_count(len(aud_tracks)),
        inst_names=[t.name for t in inst_tracks[MIXED_TEMPLATE_INSTRUMENTS:]]
        if len(inst_tracks) > MIXED_TEMPLATE_INSTRUMENTS
        else None,
        audio_names=[t.name for t in aud_tracks[MIXED_TEMPLATE_AUDIO:]]
        if len(aud_tracks) > MIXED_TEMPLATE_AUDIO
        else None,
        midi_regions=midi_regions or None,
        audio_regions=audio_regions or None,
        verbose=False,
    )

    bundle = out
    if bundle.is_dir():
        report.warnings.extend(apply_transport(bundle, project.transport, project.markers))
        _patch_region_names(bundle, audio_names)
        _apply_title(bundle, project.metadata.title)
        apply_template_track_names(
            bundle, inst_tracks=inst_tracks, aud_tracks=aud_tracks
        )
        apply_track_order(bundle, project, report)
        apply_mixer(bundle, project, report)
        export_sidecars(bundle, project, report)

    return report


def convert_file(dawproject: Path, out: Path, *, force: bool = False) -> ConversionReport:
    project = parser.load(dawproject)
    try:
        return convert(project, out, force=force)
    finally:
        parser.cleanup(project)
