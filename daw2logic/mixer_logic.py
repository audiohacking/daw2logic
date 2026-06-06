"""Apply mixer state to Logic ProjectData OCuA channel strips."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from logicx.projectdata import OCUA_UUID, ProjectData, _ocua_for_channel

from .ir import Project, Track
from .logicx_channels import channel_for_track
from .track_order import _counting_ordinals, logic_aud_ordinal, logic_inst_ordinal

# Logic-validated 2026-06 (drumloop_minus6db.logicx). Channel-strip volume:
#   @0x98 float32 LE = dB + OCUA_VOLUME_DB_OFFSET  (0 dB -> ~7.559, -6 dB -> 1.559)
# Logic ignores @0x98 unless the strip is marked active:
#   @0x4e = 0x03  (required on save / for load)
#   @0x79 = 0x3f  (unity default is 0x5a on both 0xabf7 and 0x29f5 strips)
OCUA_VOLUME_DB_OFF = 0x98
OCUA_VOLUME_DB_OFFSET = 7.5590658
OCUA_AUDIO_CFG = b"\xab\xf7"
OCUA_INST_CFG = b"\x29\xf5"
OCUA_ACTIVE_FLAG_OFF = 0x4e
OCUA_ACTIVE_FLAG_VAL = 0x03
OCUA_VOL_GATE_OFF = 0x79
OCUA_VOL_GATE_VAL = 0x3F
OCUA_AUDIO_VOLUME_DB_OFF = OCUA_VOLUME_DB_OFF  # alias
OCUA_AUDIO_VOL_GATE_OFF = OCUA_VOL_GATE_OFF
OCUA_AUDIO_VOL_GATE_VAL = OCUA_VOL_GATE_VAL

# Logic-validated 2026-06 (drumloop_pan_left.logicx, hard-left -64):
#   @0x7d uint8 = round(normalized_pan * 127)  (0.0 -> 0, 0.5 -> 64, 1.0 -> 127)
OCUA_PAN_OFF = 0x7D
# Logic-validated 2026-06 (bass_muted.logicx):
#   @0x7e = 0x01 when muted, 0x00 when unmuted
OCUA_MUTE_OFF = 0x7E
OCUA_MUTE_ON = 0x01
OCUA_MUTE_OFF_VAL = 0x00

# Logic-validated 2026-06 (drumloop_minus6db.logicx): fader display also reads ivnE:
#   @0x1a6 float32 LE = abs(attenuation_dB) / IVNE_VOLUME_DB_SCALE  (-6 dB -> ~0.01535)
#   @0xcc = 0x04 on audio channels when volume is set (default 0x02)
IVNE_VOLUME_OFF = 0x1A6
IVNE_VOLUME_ACTIVE_OFF = 0xCC
IVNE_VOLUME_ACTIVE_VAL = 0x04
IVNE_VOLUME_DB_SCALE = 6.0 / struct.unpack("<f", bytes.fromhex("80797b3c"))[0]


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


def normalized_to_logic_pan_byte(normalized: float) -> int:
    """DAWproject pan 0..1 -> Logic OCuA @0x7d (center 64, hard-left 0)."""
    return max(0, min(127, round(float(normalized) * 127)))


def logic_pan_byte_to_normalized(stored: int) -> float:
    return stored / 127.0


def linear_to_ivne_volume_float(linear: float) -> float:
    """DAWproject linear gain -> ivnE @0x1a6 (Logic fader display field)."""
    if linear <= 0:
        att_db = 100.0
    else:
        att_db = max(0.0, -20.0 * math.log10(linear))
    if att_db < 1e-6:
        return 0.0
    return att_db / IVNE_VOLUME_DB_SCALE


def _strip_cfg(raw: bytes) -> bytes | None:
    if len(raw) <= 0x72:
        return None
    cfg = raw[0x70:0x72]
    if cfg in (OCUA_AUDIO_CFG, OCUA_INST_CFG):
        return cfg
    return None


def _patch_float(raw: bytearray, offset: int, value: float) -> None:
    struct.pack_into("<f", raw, offset, float(value))


def _patch_mute(raw: bytearray, offset: int, muted: bool) -> None:
    raw[offset] = OCUA_MUTE_ON if muted else OCUA_MUTE_OFF_VAL


def patch_ocua_mixer(raw: bytes, *, volume_linear: float | None = None,
                     pan_normalized: float | None = None, mute: bool | None = None) -> bytes | None:
    """Patch one OCuA strip. Returns new bytes when at least one field was written."""
    if len(raw) < OCUA_UUID + 16 or raw[OCUA_UUID:OCUA_UUID + 16] == b"\x00" * 16:
        return None
    b = bytearray(raw)
    changed = False
    if volume_linear is not None and _strip_cfg(raw) is not None:
        b[OCUA_ACTIVE_FLAG_OFF] = OCUA_ACTIVE_FLAG_VAL
        b[OCUA_VOL_GATE_OFF] = OCUA_VOL_GATE_VAL
        _patch_float(b, OCUA_VOLUME_DB_OFF, linear_to_logic_volume_db(volume_linear))
        changed = True
    if pan_normalized is not None and OCUA_PAN_OFF is not None and _strip_cfg(raw) is not None:
        b[OCUA_PAN_OFF] = normalized_to_logic_pan_byte(pan_normalized)
        changed = True
    if mute is not None and _strip_cfg(raw) is not None:
        _patch_mute(b, OCUA_MUTE_OFF, mute)
        changed = True
    return bytes(b) if changed else None


def _ivne_for_channel(pd: ProjectData, channel: int):
    for r in pd.records:
        if r.tag != b"ivnE" or len(r.raw) <= IVNE_VOLUME_OFF + 4:
            continue
        if int.from_bytes(r.raw[8:12], "little") == channel:
            return r
    return None


def patch_ivne_volume(raw: bytes, *, volume_linear: float, is_audio: bool) -> bytes | None:
    """Patch ivnE display volume. Required alongside OCuA @0x98 for Logic fader UI."""
    if len(raw) <= IVNE_VOLUME_OFF + 3:
        return None
    b = bytearray(raw)
    _patch_float(b, IVNE_VOLUME_OFF, linear_to_ivne_volume_float(volume_linear))
    if is_audio and len(raw) > IVNE_VOLUME_ACTIVE_OFF:
        b[IVNE_VOLUME_ACTIVE_OFF] = IVNE_VOLUME_ACTIVE_VAL
    return bytes(b)


def _mixer_needs_patch(track: Track) -> bool:
    vol = track.volume is not None and abs(track.volume - 1.0) >= 1e-6
    pan = track.pan is not None and abs(track.pan - 0.5) >= 1e-6
    mute = track.mute is True
    return vol or pan or mute


def apply_mixer(logicx_dir: Path, project: Project, report) -> None:
    """Write mixer fields into ProjectData OCuA strips (volume, pan, mute native)."""
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
        patch_kwargs: dict = {}
        if track.volume is not None and abs(track.volume - 1.0) >= 1e-6:
            patch_kwargs["volume_linear"] = track.volume
        if track.pan is not None and abs(track.pan - 0.5) >= 1e-6:
            patch_kwargs["pan_normalized"] = track.pan
        if track.mute is True:
            patch_kwargs["mute"] = True
        new_raw = patch_ocua_mixer(
            oc.raw,
            **patch_kwargs,
        )
        if new_raw is None:
            report.warnings.append(
                f"track '{track.name}': mixer patch skipped (unsupported strip type)"
            )
            continue
        oc.raw = new_raw
        if "volume_linear" in patch_kwargs:
            iv = _ivne_for_channel(pd, ch)
            if iv is not None:
                iv_new = patch_ivne_volume(
                    iv.raw,
                    volume_linear=patch_kwargs["volume_linear"],
                    is_audio=not has_midi,
                )
                if iv_new is not None:
                    iv.raw = iv_new
        patched += 1
        report.mixer_patched_tracks.add(track.name)

    if patched:
        pd_path.write_bytes(pd.serialize())
