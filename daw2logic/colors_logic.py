"""Apply DAWproject track/region colors to Logic ProjectData."""

from __future__ import annotations

import struct
from pathlib import Path

from .colors import nearest_logic_picker_index, qesm_track_color_bytes, region_color_bytes
from .ir import Project

# Logic-validated 2026-06 (color_baseline.logicx / color_changed.logicx, bitwig_simple).
QESM_IDX_OFF = 0x08
QESM_COLOR_U32_OFF = 0x2C
QESM_COLOR_AUX_OFF = 0x10E
GRUA_COLOR_FLAG_OFF = 0x27
GRUA_COLOR_FLAG_CUSTOM = 0x10
GRUA_COLOR_FLAG_DEFAULT = 0x20
GRUA_COLOR_BLOB_OFF = 0x4E
GRUA_COLOR_BLOB_LEN = 8


def patch_qesm_track_color(raw: bytes, *, picker_index: int, channel: int) -> bytes:
    """Return qeSM bytes with Logic arrange track color for `picker_index`."""
    b = bytearray(raw)
    u32, aux = qesm_track_color_bytes(picker_index, channel)
    struct.pack_into("<I", b, QESM_COLOR_U32_OFF, u32)
    b[QESM_COLOR_AUX_OFF] = aux
    return bytes(b)


def patch_grua_region_color(raw: bytes, *, hex_color: str) -> bytes:
    b = bytearray(raw)
    b[GRUA_COLOR_FLAG_OFF] = GRUA_COLOR_FLAG_CUSTOM
    blob = region_color_bytes(hex_color)
    b[GRUA_COLOR_BLOB_OFF : GRUA_COLOR_BLOB_OFF + GRUA_COLOR_BLOB_LEN] = blob
    return bytes(b)


def apply_colors(
    logicx_dir: Path,
    project: Project,
    report,
    *,
    region_colors: list[str | None] | None = None,
) -> None:
    """Write track/region colors when Logic-validated encodings are known.

    synthesize_av_region_bundle already assigns per-track qeSM colors in the
    template. Overwriting qeSM/gRuA with unvalidated picker encodings corrupts
    the bundle (Logic: "song is corrupted"). Until RE maps picker index → qeSM
    bytes for arbitrary colors, colors stay in the sidecar manifest only.
    """
    _ = logicx_dir, region_colors, nearest_logic_picker_index  # future native graft

    colored_tracks = [t.name for t in project.tracks if t.color]
    colored_clips = sum(
        1 for t in project.tracks for c in (*t.midi_clips, *t.audio_clips) if c.color
    )
    if not colored_tracks and not colored_clips:
        return

    if colored_tracks:
        report.warnings.append(
            f"{len(colored_tracks)} track color(s) exported to sidecar only "
            "(native qeSM encoding not validated for this palette)"
        )
    if colored_clips:
        report.warnings.append(
            f"{colored_clips} clip color(s) exported to sidecar only "
            "(native gRuA encoding not validated)"
        )
