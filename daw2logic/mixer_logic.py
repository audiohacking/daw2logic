"""Apply mixer state to Logic ProjectData OCuA channel strips."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from logicx.projectdata import OCUA_UUID, ProjectData, _ocua_for_channel

from .ir import Project, Track
from .logicx_channels import channel_for_track
from .track_order import _counting_ordinals, logic_aud_ordinal, logic_inst_ordinal

# Logic-validated 2026-06 (re_vol.logicx: -6 dB on an audio strip -> float 1.559 @0x98).
# Encoding: float32 LE stored = dB + OCUA_VOLUME_DB_OFFSET  (0 dB -> ~7.559, -6 dB -> 1.559).
OCUA_AUDIO_VOLUME_DB_OFF = 0x98
OCUA_VOLUME_DB_OFFSET = 7.5590658
OCUA_AUDIO_CFG = b"\xab\xf7"
OCUA_INST_CFG = b"\x29\xf5"

# @0x4e 00->03 on save across all strips — touch/session flag, NOT fader level.
OCUA_TOUCH_FLAG_OFF = 0x4e

OCUA_PAN_OFF: int | None = None
OCUA_MUTE_OFF: int | None = None


def linear_to_logic_volume_db(linear: float) -> float:
    """DAWproject linear gain -> Logic OCuA float @0x98 (audio strips)."""
    if linear <= 0:
        db = -100.0
    else:
        db = 20.0 * math.log10(linear)
    return db + OCUA_VOLUME_DB_OFFSET


def logic_volume_db_to_linear(stored: float) -> float:
    db = stored - OCUA_VOLUME_DB_OFFSET
    if db <= -100.0:
        return 0.0
    return 10.0 ** (db / 20.0)


def _is_audio_strip(raw: bytes) -> bool:
    return len(raw) > 0x72 and raw[0x70:0x72] == OCUA_AUDIO_CFG


def _patch_float(raw: bytearray, offset: int, value: float) -> None:
    struct.pack_into("<f", raw, offset, float(value))


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
    if volume_linear is not None and _is_audio_strip(raw):
        _patch_float(b, OCUA_AUDIO_VOLUME_DB_OFF, linear_to_logic_volume_db(volume_linear))
        changed = True
    if pan_normalized is not None and OCUA_PAN_OFF is not None:
        _patch_float(b, OCUA_PAN_OFF, pan_normalized)
        changed = True
    if mute is not None and OCUA_MUTE_OFF is not None:
        changed |= _patch_mute(b, OCUA_MUTE_OFF, mute)
    return bytes(b) if changed else None


def _mixer_needs_patch(track: Track) -> bool:
    vol = track.volume is not None and abs(track.volume - 1.0) >= 1e-6
    pan = track.pan is not None and abs(track.pan - 0.5) >= 1e-6
    mute = track.mute is True
    return vol or pan or mute


def apply_mixer(logicx_dir: Path, project: Project, report) -> None:
    """Write mixer fields into ProjectData OCuA strips (audio volume native; inst TBD)."""
    pd_path = logicx_dir / "Alternatives" / "000" / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())
    ordinals = _counting_ordinals(project)
    patched = 0

    for track in project.tracks:
        if not _mixer_needs_patch(track):
            continue
        inst_ord, aud_ord, has_midi = ordinals[track.id]
        if has_midi and inst_ord is not None:
            inst_ord = logic_inst_ordinal(inst_ord)
        elif aud_ord is not None:
            aud_ord = logic_aud_ordinal(aud_ord)
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
        if has_midi and track.volume is not None and oc.raw[0x70:0x72] == OCUA_INST_CFG:
            report.warnings.append(
                f"track '{track.name}': instrument strip volume not RE'd yet (sidecar only)"
            )
            continue
        new_raw = patch_ocua_mixer(
            oc.raw,
            volume_linear=track.volume,
            pan_normalized=track.pan,
            mute=track.mute,
        )
        if new_raw is None:
            report.warnings.append(
                f"track '{track.name}': mixer patch skipped (unsupported strip type)"
            )
            continue
        oc.raw = new_raw
        patched += 1
        report.mixer_patched_tracks.add(track.name)

    if patched:
        pd_path.write_bytes(pd.serialize())
