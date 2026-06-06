"""Apply mixer state to Logic ProjectData OCuA channel strips (when offsets are known)."""

from __future__ import annotations

import struct
from pathlib import Path

from logicx.projectdata import OCUA_UUID, ProjectData, _ocua_for_channel

from .ir import Project, Track
from .logicx_channels import channel_for_track

# Unverified until differential RE against Logic-made fixtures (see tools/ocua_mixer_re.py).
OCUA_VOLUME_LINEAR_OFF: int | None = None
OCUA_PAN_OFF: int | None = None
OCUA_MUTE_OFF: int | None = None


def _linear_to_db(linear: float) -> float:
    if linear <= 0:
        return -100.0
    import math
    return 20.0 * math.log10(linear)


def _patch_float(raw: bytearray, offset: int | None, value: float) -> bool:
    if offset is None or offset + 4 > len(raw):
        return False
    struct.pack_into("<f", raw, offset, float(value))
    return True


def _patch_mute(raw: bytearray, offset: int | None, muted: bool) -> bool:
    if offset is None or offset >= len(raw):
        return False
    raw[offset] = 1 if muted else 0
    return True


def patch_ocua_mixer(raw: bytes, *, volume_linear: float | None = None,
                     pan_normalized: float | None = None, mute: bool | None = None) -> bytes | None:
    """Patch one OCuA strip. Returns new bytes when at least one field was written."""
    if len(raw) < OCUA_UUID + 16 or raw[OCUA_UUID:OCUA_UUID + 16] == b"\x00" * 16:
        return None
    b = bytearray(raw)
    changed = False
    if volume_linear is not None and OCUA_VOLUME_LINEAR_OFF is not None:
        changed |= _patch_float(b, OCUA_VOLUME_LINEAR_OFF, volume_linear)
    if pan_normalized is not None and OCUA_PAN_OFF is not None:
        # DAWproject pan is 0=left, 0.5=center, 1=right; Logic encoding TBD.
        changed |= _patch_float(b, OCUA_PAN_OFF, pan_normalized)
    if mute is not None and OCUA_MUTE_OFF is not None:
        changed |= _patch_mute(b, OCUA_MUTE_OFF, mute)
    return bytes(b) if changed else None


def _track_ordinals(project: Project) -> dict[str, tuple[int | None, int | None, bool]]:
    """track id -> (inst_ordinal, aud_ordinal, has_midi)."""
    inst_n, aud_n = 0, 0
    out: dict[str, tuple[int | None, int | None, bool]] = {}
    for track in project.tracks:
        has_midi = bool(track.midi_clips)
        has_audio = bool(track.audio_clips)
        inst_ord = aud_ord = None
        if has_midi:
            inst_n += 1
            inst_ord = inst_n
        if has_audio:
            aud_n += 1
            aud_ord = aud_n
        out[track.id] = (inst_ord, aud_ord, has_midi)
    return out


def _mixer_needs_patch(track: Track) -> bool:
    vol = track.volume is not None and abs(track.volume - 1.0) >= 1e-6
    pan = track.pan is not None and abs(track.pan - 0.5) >= 1e-6
    mute = track.mute is True
    return vol or pan or mute


def apply_mixer(logicx_dir: Path, project: Project, report) -> None:
    """Write mixer fields into ProjectData when OCuA offsets are configured."""
    if OCUA_VOLUME_LINEAR_OFF is None and OCUA_PAN_OFF is None and OCUA_MUTE_OFF is None:
        return

    pd_path = logicx_dir / "Alternatives" / "000" / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())
    ordinals = _track_ordinals(project)
    patched = 0

    for track in project.tracks:
        if not _mixer_needs_patch(track):
            continue
        inst_ord, aud_ord, has_midi = ordinals[track.id]
        ch = channel_for_track(
            pd, has_midi=has_midi, inst_ordinal=inst_ord, aud_ordinal=aud_ord
        )
        if ch is None:
            report.warnings.append(f"track '{track.name}': could not resolve Logic channel for mixer")
            continue
        oc = _ocua_for_channel(pd, ch)
        if oc is None:
            report.warnings.append(f"track '{track.name}': no OCuA strip for channel 0x{ch:x}")
            continue
        new_raw = patch_ocua_mixer(
            oc.raw,
            volume_linear=track.volume,
            pan_normalized=track.pan,
            mute=track.mute,
        )
        if new_raw is None:
            report.warnings.append(
                f"track '{track.name}': mixer patch skipped (unknown OCuA field encoding)"
            )
            continue
        oc.raw = new_raw
        patched += 1

    if patched:
        pd_path.write_bytes(pd.serialize())
