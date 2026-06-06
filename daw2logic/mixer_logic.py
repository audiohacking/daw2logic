"""Apply mixer state to Logic ProjectData OCuA channel strips."""

from __future__ import annotations

import math
import struct
from pathlib import Path

from logicx.projectdata import OCUA_UUID, ProjectData, _ocua_for_channel

from .ir import Project, Track
from .logicx_channels import channel_for_track
from .track_order import _counting_ordinals, logic_aud_ordinal, logic_inst_ordinal

# Logic-validated 2026-06 (volume_sweep_baseline.logicx). Fader volume uses paired bytes:
#   @0x79 gate byte MUST equal float32 @0x98 byte @0x9b (LE).
#   @0x4e = 0x03 required. Unity 0 dB: @0x79=0x5a, @0x98=0000005a.
# Logic maps @0x79 through a piecewise-linear table (NOT IEEE dB from @0x98).
# Captured anchors (dB, gate, @0x98 bytes):
#   -6 -> 0x3f 3c8fc73f   -3 -> 0x4b 7abeb94b   0 -> 0x5a 0000005a
#   +3 -> 0x6a 6017f76a   +6 -> 0x7f 0000007f
# Other levels: interpolate gate from anchors; lerp anchor @0x98 bodies (clamp extrap).
OCUA_VOLUME_DB_OFF = 0x98
OCUA_VOLUME_FLOAT_TAIL = 0x9B
OCUA_VOLUME_DB_OFFSET = 7.5590658
OCUA_UNITY_GATE = 0x5A
OCUA_UNITY_VOLUME_BYTES = bytes.fromhex("0000005a")
OCUA_VOLUME_CAPTURES: tuple[tuple[float, int, bytes], ...] = (
    (-6.0, 0x3F, bytes.fromhex("3c8fc73f")),
    (-3.0, 0x4B, bytes.fromhex("7abeb94b")),
    (0.0, 0x5A, OCUA_UNITY_VOLUME_BYTES),
    (3.0, 0x6A, bytes.fromhex("6017f76a")),
    (6.0, 0x7F, bytes.fromhex("0000007f")),
)
OCUA_VOLUME_CAPTURE_TOLERANCE_DB = 0.08
# (Logic fader display dB, @0x79 gate). Sweep anchors + user-validated bitwig_simple checks.
OCUA_GATE_CALIBRATION: tuple[tuple[float, int], ...] = (
    (-20.5, 0x1B),  # gate 0x1b + -6 body
    (-14.7, 0x26),  # bitwig_simple Drumloop @ -15 dB DAW (2026-06)
    (-13.4, 0x29),  # prior drum encode overshot high
    (-6.0, 0x3F),
    (-3.0, 0x4B),
    (0.0, 0x5A),
    (3.0, 0x6A),
    (6.0, 0x7F),
)
OCUA_AUDIO_CFG = b"\xab\xf7"
OCUA_INST_CFG = b"\x29\xf5"
OCUA_ACTIVE_FLAG_OFF = 0x4e
OCUA_ACTIVE_FLAG_VAL = 0x03
OCUA_VOL_GATE_OFF = 0x79
OCUA_AUDIO_VOLUME_DB_OFF = OCUA_VOLUME_DB_OFF  # alias
OCUA_AUDIO_VOL_GATE_OFF = OCUA_VOL_GATE_OFF

# Logic-validated 2026-06 (drumloop_pan_left.logicx, hard-left -64):
#   @0x7d uint8 = round(normalized_pan * 127)  (0.0 -> 0, 0.5 -> 64, 1.0 -> 127)
OCUA_PAN_OFF = 0x7D
# Logic-validated 2026-06 (bass_muted.logicx):
#   @0x7e = 0x01 when muted, 0x00 when unmuted
OCUA_MUTE_OFF = 0x7E
OCUA_MUTE_ON = 0x01
OCUA_MUTE_OFF_VAL = 0x00

# Logic-validated 2026-06 (drumloop_minus6db.logicx): also written on Logic volume save:
#   @0x48 float32 LE = -attenuation_dB / 17  (-6 dB -> ~-0.353)
#   @0x26 = 0x14, @0x4f = 0x0c when mixer edited (volume/pan/mute)
KART_ARRANGE_TAG = 0x040000
KART_VOL_DISPLAY_OFF = 0x48
KART_VOL_DB_DIVISOR = 17.0
KART_TOUCH_OFF = 0x26
KART_TOUCH_VAL = 0x14
KART_MIXER_TOUCH_OFF = 0x4F
KART_MIXER_TOUCH_VAL = 0x0C

# Secondary ivnE field (also written on Logic volume save; keep in sync):
IVNE_VOLUME_OFF = 0x1A6
IVNE_VOLUME_ACTIVE_OFF = 0xCC
IVNE_VOLUME_ACTIVE_VAL = 0x04
IVNE_VOLUME_DB_SCALE = 6.0 / struct.unpack("<f", bytes.fromhex("80797b3c"))[0]


def _attenuation_db(linear: float) -> float:
    if linear <= 0:
        return 100.0
    return max(0.0, -20.0 * math.log10(linear))


def linear_to_logic_volume_db(linear: float) -> float:
    """DAWproject linear gain -> Logic OCuA float @0x98."""
    if linear <= 0:
        db = -100.0
    else:
        db = 20.0 * math.log10(linear)
    return db + OCUA_VOLUME_DB_OFFSET


def _target_db_from_linear(linear: float) -> float:
    if linear <= 0:
        return -100.0
    return 20.0 * math.log10(linear)


def _interpolate_gate_db(target_db: float) -> int:
    """Piecewise-linear @0x79 gate from measured Logic display calibration."""
    pts = OCUA_GATE_CALIBRATION
    if target_db <= pts[0][0]:
        d0, g0 = pts[0]
        d1, g1 = pts[1]
    elif target_db >= pts[-1][0]:
        d0, g0 = pts[-2]
        d1, g1 = pts[-1]
    else:
        for (d0, g0), (d1, g1) in zip(pts, pts[1:]):
            if d0 <= target_db <= d1:
                break
        else:
            return pts[-1][1]
    if d1 == d0:
        return g0
    t = (target_db - d0) / (d1 - d0)
    return max(0, min(255, round(g0 + t * (g1 - g0))))


def _lerp_volume_bytes(b0: bytes, b1: bytes, t: float) -> bytes:
    return bytes(
        max(0, min(255, round(b0[i] + t * (b1[i] - b0[i]))))
        for i in range(4)
    )


def _volume_bytes_for_db(target_db: float, gate: int) -> bytes:
    """Build @0x98 bytes with @0x9b == gate from anchor interpolation."""
    pts = sorted(OCUA_VOLUME_CAPTURES, key=lambda row: row[0])
    if target_db <= pts[0][0]:
        base = pts[0][2]
        return base[:3] + bytes([gate])
    if target_db >= pts[-1][0]:
        base = pts[-1][2]
        return base[:3] + bytes([gate])
    for (d0, _, b0), (d1, _, b1) in zip(pts, pts[1:]):
        if d0 <= target_db <= d1:
            t = (target_db - d0) / (d1 - d0)
            body = _lerp_volume_bytes(b0, b1, t)
            return body[:3] + bytes([gate])
    base = pts[0][2]
    return base[:3] + bytes([gate])


def encode_ocua_volume(linear: float) -> tuple[int, bytes]:
    """Return (@0x79 gate, @0x98..0x9b float bytes) for Logic fader display."""
    if abs(linear - 1.0) < 1e-6:
        return OCUA_UNITY_GATE, OCUA_UNITY_VOLUME_BYTES
    target_db = _target_db_from_linear(linear)
    for db, gate, vol_bytes in OCUA_VOLUME_CAPTURES:
        if abs(db - target_db) <= OCUA_VOLUME_CAPTURE_TOLERANCE_DB:
            return gate, vol_bytes
    gate = _interpolate_gate_db(target_db)
    return gate, _volume_bytes_for_db(target_db, gate)


def encode_ocua_volume_bytes(linear: float) -> bytes:
    """4-byte float for OCuA @0x98 (gate byte is separate @0x79)."""
    return encode_ocua_volume(linear)[1]


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


def linear_to_kart_volume_display(linear: float) -> float:
    """DAWproject linear gain -> karT @0x48 (Logic fader display)."""
    att_db = _attenuation_db(linear)
    if att_db < 1e-6:
        return 0.0
    return -att_db / KART_VOL_DB_DIVISOR


def linear_to_ivne_volume_float(linear: float) -> float:
    """DAWproject linear gain -> ivnE @0x1a6 (companion volume field)."""
    att_db = _attenuation_db(linear)
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
        gate, vol_bytes = encode_ocua_volume(volume_linear)
        b[OCUA_VOL_GATE_OFF] = gate
        b[OCUA_VOLUME_DB_OFF:OCUA_VOLUME_DB_OFF + 4] = vol_bytes
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


def _kart_arrange_for_channel(pd: ProjectData, channel: int):
    for r in pd.records:
        if r.tag != b"karT" or len(r.raw) != 93:
            continue
        if int.from_bytes(r.raw[8:12], "little") != KART_ARRANGE_TAG:
            continue
        if int.from_bytes(r.raw[0x2A:0x2E], "little") == channel:
            return r
    return None


def patch_ivne_volume(raw: bytes, *, volume_linear: float, is_audio: bool) -> bytes | None:
    if len(raw) <= IVNE_VOLUME_OFF + 3:
        return None
    b = bytearray(raw)
    struct.pack_into("<f", b, IVNE_VOLUME_OFF, linear_to_ivne_volume_float(volume_linear))
    if is_audio and len(raw) > IVNE_VOLUME_ACTIVE_OFF:
        b[IVNE_VOLUME_ACTIVE_OFF] = IVNE_VOLUME_ACTIVE_VAL
    return bytes(b)


def patch_kart_mixer(
    raw: bytes,
    *,
    volume_linear: float | None = None,
    touch: bool = False,
) -> bytes | None:
    """Patch karT arrange row mixer display / touch flags."""
    if len(raw) != 93:
        return None
    b = bytearray(raw)
    changed = False
    if volume_linear is not None:
        struct.pack_into("<f", b, KART_VOL_DISPLAY_OFF, linear_to_kart_volume_display(volume_linear))
        changed = True
    if touch or volume_linear is not None:
        b[KART_TOUCH_OFF] = KART_TOUCH_VAL
        b[KART_MIXER_TOUCH_OFF] = KART_MIXER_TOUCH_VAL
        changed = True
    return bytes(b) if changed else None


def _mixer_needs_patch(track: Track) -> bool:
    vol = track.volume is not None and abs(track.volume - 1.0) >= 1e-6
    pan = track.pan is not None and abs(track.pan - 0.5) >= 1e-6
    mute = track.mute is True
    return vol or pan or mute


def apply_mixer(logicx_dir: Path, project: Project, report) -> None:
    """Write mixer fields into ProjectData (OCuA gain + karT / ivnE companions)."""
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
        new_raw = patch_ocua_mixer(oc.raw, **patch_kwargs)
        if new_raw is None:
            report.warnings.append(
                f"track '{track.name}': mixer patch skipped (unsupported strip type)"
            )
            continue
        oc.raw = new_raw

        kart = _kart_arrange_for_channel(pd, ch)
        if kart is not None:
            kart_new = patch_kart_mixer(
                kart.raw,
                volume_linear=patch_kwargs.get("volume_linear"),
                touch=bool(
                    patch_kwargs.get("pan_normalized") is not None
                    or patch_kwargs.get("mute")
                ),
            )
            if kart_new is not None:
                kart.raw = kart_new

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
