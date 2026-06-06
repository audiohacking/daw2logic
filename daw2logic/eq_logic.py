"""Graft Logic Channel EQ (UCuA PST) from RE-validated donor bytes."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from logicx.projectdata import ProjectData, Record

from .eq import LOGIC_EQ_TYPES
from .ir import EqBand, EqualizerInfo, Project
from .logicx_channels import channel_for_track
from .track_order import logic_aud_ordinal, logic_inst_ordinal

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "channel_eq"

# Per-band PST float indices (RE: eq_baseline.logicx UCuA-464 vs Logic CST default).
PST_BAND_FIELDS: tuple[dict[str, int], ...] = (
    {"freq": 10, "gain": 11, "q": 12, "on": 13},
    {"freq": 18, "gain": 15, "q": 16, "on": 17},
    {"freq": 22, "gain": 23, "q": 20, "on": 21},
    {"freq": 26, "gain": 27, "q": 28, "on": 29},
    {"freq": 30, "gain": 31, "q": 32, "on": 33},
    {"freq": 35, "gain": 36, "q": 37, "on": 38},
)

PST_DEFAULT_FREQS = (100.0, 250.0, 1040.0, 2500.0, 7500.0, 20000.0)
PLUGIN_SLOT_BASE = 0x400000
NCUA_MAIN_LEN = 2128


def plugin_slot_idx(channel: int) -> int:
    return channel - PLUGIN_SLOT_BASE


def _u32(raw: bytes, off: int) -> int:
    return struct.unpack_from("<I", raw, off)[0]


def _set_u32(buf: bytearray, off: int, val: int) -> None:
    struct.pack_into("<I", buf, off, val)


def _load_fixture(name: str) -> bytes:
    path = _FIXTURES / name
    if not path.is_file():
        raise FileNotFoundError(f"missing EQ fixture {path}")
    return path.read_bytes()


def _ncua_patches() -> list[tuple[int, int]]:
    raw = json.loads((_FIXTURES / "ncua_2128_patches.json").read_text())
    return [(int(i), int(v)) for i, _o, v in raw]


def _has_channel_eq_ucua(pd: ProjectData, plugin_idx: int) -> bool:
    for r in pd.records:
        if (
            r.tag == b"UCuA"
            and len(r.raw) == 464
            and _u32(r.raw, 0x08) == plugin_idx
            and b"Channel EQ" in r.raw
        ):
            return True
    return False


def _find_ncua_main(pd: ProjectData, plugin_idx: int) -> Record | None:
    for r in pd.records:
        if (
            r.tag == b"nCuA"
            and len(r.raw) == NCUA_MAIN_LEN
            and _u32(r.raw, 0x08) == plugin_idx
        ):
            return r
    return None


def _channel_eq_ucua(pd: ProjectData, plugin_idx: int) -> Record | None:
    for r in pd.records:
        if (
            r.tag == b"UCuA"
            and len(r.raw) == 464
            and _u32(r.raw, 0x08) == plugin_idx
            and b"Channel EQ" in r.raw
        ):
            return r
    return None


def _stamp_plugin_idx(raw: bytes, plugin_idx: int) -> bytes:
    b = bytearray(raw)
    _set_u32(b, 0x08, plugin_idx)
    return bytes(b)


def _nearest_band(freq_hz: float | None) -> int:
    """Return 1-based Logic parametric band index closest to ``freq_hz``."""
    if freq_hz is None or freq_hz <= 0:
        return 1
    best_i, best_d = 1, float("inf")
    for j, df in enumerate(PST_DEFAULT_FREQS, start=1):
        d = abs(freq_hz - df)
        if d < best_d:
            best_d = d
            best_i = j
    return best_i


def _band_float_indices(band_index: int) -> dict[str, int]:
    if 1 <= band_index <= len(PST_BAND_FIELDS):
        return PST_BAND_FIELDS[band_index - 1]
    return PST_BAND_FIELDS[-1]


def patch_channel_eq_pst(raw_ucua_464: bytes, eq: EqualizerInfo) -> bytes:
    """Return UCuA-464 bytes with Channel EQ PST floats updated from ``eq``."""
    b = bytearray(raw_ucua_464)
    pos = b.find(b"GAMETSPP")
    if pos < 12:
        raise ValueError("Channel EQ UCuA missing GAMETSPP PST")
    payload_off = pos + 12

    used: set[int] = set()
    for band in eq.bands:
        if band.enabled is False:
            continue
        logic_type = LOGIC_EQ_TYPES.get(band.band_type, "parametric")
        if logic_type == "low_cut":
            continue
        bi = _nearest_band(band.frequency_hz)
        while bi in used and bi < len(PST_BAND_FIELDS):
            bi += 1
        if bi > len(PST_BAND_FIELDS):
            break
        used.add(bi)
        fields = _band_float_indices(bi)
        for key, fidx in fields.items():
            byte_off = payload_off + fidx * 4
            if byte_off + 4 > len(b):
                break
            if key == "freq" and band.frequency_hz is not None:
                struct.pack_into("<f", b, byte_off, float(band.frequency_hz))
            elif key == "gain" and band.gain_db is not None:
                struct.pack_into("<f", b, byte_off, float(band.gain_db))
            elif key == "q" and band.q is not None:
                struct.pack_into("<f", b, byte_off, float(band.q))
            elif key == "on":
                struct.pack_into("<f", b, byte_off, 1.0 if band.enabled is not False else 0.0)

    return bytes(b)


def _insert_after(records: list, anchor: Record, new_records: list[Record]) -> None:
    idx = records.index(anchor)
    for offset, rec in enumerate(new_records, start=1):
        records.insert(idx + offset, rec)


def graft_channel_eq(pd: ProjectData, plugin_idx: int, eq: EqualizerInfo) -> bool:
    """Insert Channel EQ UCuA cluster + patch nCuA for ``plugin_idx``. Returns True if changed."""
    if _has_channel_eq_ucua(pd, plugin_idx):
        ucua = _channel_eq_ucua(pd, plugin_idx)
        assert ucua is not None
        ucua.raw = patch_channel_eq_pst(ucua.raw, eq)
        return True

    ncua = _find_ncua_main(pd, plugin_idx)
    if ncua is None:
        return False

    # Patch slot metadata on the 2128-byte nCuA container.
    nb = bytearray(ncua.raw)
    for off, val in _ncua_patches():
        if off < len(nb):
            nb[off] = val
    ncua.raw = bytes(nb)

    # Replace the active OCuA strip (first @0x4e==0x03 in the plugin run) with 241-byte donor.
    strip241 = _load_fixture("ocua_241.bin")
    strip241 = _stamp_plugin_idx(strip241, plugin_idx)
    ocua_active: Record | None = None
    past_ncua = False
    for r in pd.records:
        if r is ncua:
            past_ncua = True
            continue
        if not past_ncua:
            continue
        if r.tag == b"OCuA" and _u32(r.raw, 0x08) == plugin_idx:
            if len(r.raw) == 205 and r.raw[0x4E] == 0x03:
                ocua_active = r
                break
        if r.tag in (b"nCuA", b"UCuA") and _u32(r.raw, 0x08) != plugin_idx:
            break

    if ocua_active is None:
        return False

    ocua_active.raw = strip241

    new_ucua = [
        Record(b"UCuA", _stamp_plugin_idx(_load_fixture(f"ucua_{sz}.bin"), plugin_idx))
        for sz in (464, 339, 384)
    ]
    new_ucua[0] = Record(b"UCuA", patch_channel_eq_pst(new_ucua[0].raw, eq))
    _insert_after(pd.records, ocua_active, new_ucua)
    return True


def apply_eq(logicx_dir: Path, project: Project, report) -> None:
    """Write native Logic Channel EQ for tracks that carry DAWproject Equalizer data."""
    pd_path = logicx_dir / "Alternatives" / "000" / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())
    changed = False
    inst_i = aud_i = 0

    for track in project.tracks:
        if not track.equalizers:
            continue
        has_midi = bool(track.midi_clips)
        has_audio = bool(track.audio_clips)
        inst_ord = logic_inst_ordinal(inst_i + 1) if has_midi else None
        aud_ord = logic_aud_ordinal(aud_i + 1) if has_audio else None
        if has_midi:
            inst_i += 1
        if has_audio:
            aud_i += 1

        ch = channel_for_track(
            pd,
            has_midi=has_midi,
            inst_ordinal=inst_ord if has_midi else None,
            aud_ordinal=aud_ord if has_audio else None,
        )
        if ch is None:
            report.warnings.append(f"track '{track.name}': no Logic channel for EQ graft")
            continue

        slot = plugin_slot_idx(ch)
        ncua = _find_ncua_main(pd, slot)
        if ncua is None:
            report.warnings.append(
                f"track '{track.name}': no 2128-byte nCuA container — EQ sidecar only"
            )
            continue

        # Merge multiple Equalizer devices into one Channel EQ (first wins for metadata).
        merged = EqualizerInfo(
            name=track.equalizers[0].name,
            device_id=track.equalizers[0].device_id,
            enabled=all(e.enabled for e in track.equalizers),
            bands=tuple(b for e in track.equalizers for b in e.bands),
            input_gain_db=track.equalizers[0].input_gain_db,
            output_gain_db=track.equalizers[0].output_gain_db,
        )
        if graft_channel_eq(pd, slot, merged):
            report.eq_patched_tracks.add(track.name)
            changed = True
        else:
            report.warnings.append(f"track '{track.name}': Channel EQ graft failed")

    if changed:
        pd_path.write_bytes(pd.serialize())
