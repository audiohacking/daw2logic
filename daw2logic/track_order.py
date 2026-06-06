"""Map DAWproject tracks to Logic ordinals and arrange-row order."""

from __future__ import annotations

import struct

from logicx.projectdata import (
    ARR_ORDER_IDX,
    ARR_ORDER_ROW0,
    ARR_ROW_H,
    KART_BLK,
    KART_CHAN,
    KART_MASTER_CHAN,
    KART_ORD,
    ProjectData,
    REC_HEADER_SIZE,
    REC_SIZE_OFF,
    TRK_FIXED,
    TRK_IDX,
    TRK_RANK,
    TRK_SLOT,
    _arrange_container,
    _arr_height_off,
    _u32,
)

from .ir import Project, Track
from .logicx_channels import audio_channels, instrument_channels

# Tracks pre-seeded in the baked mixed template (LogicProFormatWriter mixed_base).
MIXED_TEMPLATE_INSTRUMENTS = 1
MIXED_TEMPLATE_AUDIO = 1


def is_interleaved(project: Project) -> bool:
    """True when an audio track appears before a later instrument track in the source."""
    aud_seen = False
    for track in project.tracks:
        if track.midi_clips and aud_seen:
            return True
        if track.audio_clips:
            aud_seen = True
    return False


def _counting_ordinals(project: Project) -> dict[str, tuple[int | None, int | None, bool]]:
    """Per-track 1-based ordinals within exported inst/audio lists (no template offset)."""
    inst_n = aud_n = 0
    out: dict[str, tuple[int | None, int | None, bool]] = {}
    for track in project.tracks:
        inst_ord = aud_ord = None
        has_midi = bool(track.midi_clips)
        if has_midi:
            inst_n += 1
            inst_ord = inst_n
        if track.audio_clips:
            aud_n += 1
            aud_ord = aud_n
        out[track.id] = (inst_ord, aud_ord, has_midi)
    return out


def logic_inst_ordinal(export_index: int) -> int:
    return MIXED_TEMPLATE_INSTRUMENTS + export_index


def logic_aud_ordinal(export_index: int) -> int:
    return MIXED_TEMPLATE_AUDIO + export_index


def exported_tracks(project: Project) -> list[Track]:
    return [t for t in project.tracks if t.midi_clips or t.audio_clips]


def export_channel_order(pd: ProjectData, project: Project) -> list[int]:
    """Environment channel idx values for exported tracks in DAWproject track order."""
    inst_map = instrument_channels(pd)
    aud_map = audio_channels(pd)
    ordinals = _counting_ordinals(project)
    channels: list[int] = []
    for track in exported_tracks(project):
        inst_ord, aud_ord, has_midi = ordinals[track.id]
        if has_midi and inst_ord is not None:
            ch = inst_map.get(logic_inst_ordinal(inst_ord))
        elif aud_ord is not None:
            ch = aud_map.get(logic_aud_ordinal(aud_ord))
        else:
            ch = None
        if ch is None:
            raise ValueError(f"no Logic channel for exported track '{track.name}'")
        channels.append(ch)
    return channels


def _template_prefix_channels(pd: ProjectData) -> list[int]:
    """Mixed-template placeholder tracks that precede synthesized content."""
    prefix: list[int] = []
    for _, ch in _arrange_row_channels(pd):
        if ch in prefix:
            continue
        if len(prefix) < MIXED_TEMPLATE_INSTRUMENTS + MIXED_TEMPLATE_AUDIO:
            prefix.append(ch)
        if len(prefix) >= MIXED_TEMPLATE_INSTRUMENTS + MIXED_TEMPLATE_AUDIO:
            break
    return prefix


def _arrange_row_channels(pd: ProjectData) -> list[tuple[int, int]]:
    """[(record_index, channel)] for non-master arrange rows in stream order."""
    rows: list[tuple[int, int]] = []
    for i, rec in enumerate(pd.records):
        if rec.tag != b"karT" or len(rec.raw) != 93:
            continue
        if _u32(rec.raw, 0x08) != 0x040000:
            continue
        ch = _u32(rec.raw, KART_CHAN)
        if ch == KART_MASTER_CHAN:
            continue
        rows.append((i, ch))
    return rows


def _channel_positions(rows: list[tuple[int, int]]) -> dict[int, int]:
    return {ch: pos for pos, (_, ch) in enumerate(rows, start=1)}


def _kart_blk(ordinal: int) -> bytes:
    return bytes([0xFF, 0xFF, ordinal & 0xFF, 0x00, 0x00, 0x00, 0x02, 0x00])


def _reorder_arrange_rows(pd: ProjectData, desired_channels: list[int]) -> dict[int, int]:
    """Reorder non-master arrange rows to `desired_channels`; return old_pos -> new_pos."""
    rows = _arrange_row_channels(pd)
    if not rows:
        return {}
    indices = [i for i, _ in rows]
    by_ch = {ch: pd.records[i] for i, ch in rows}
    if set(desired_channels) != set(by_ch):
        missing = set(desired_channels) - set(by_ch)
        raise ValueError(f"arrange reorder missing channels: {[hex(c) for c in missing]}")
    old_pos = _channel_positions(rows)
    new_records = [by_ch[ch] for ch in desired_channels]
    for idx, rec in zip(indices, new_records):
        pd.records[idx] = rec
    for ord_i, ch in enumerate(desired_channels, start=1):
        rec = by_ch[ch]
        raw = bytearray(rec.raw)
        raw[KART_BLK : KART_BLK + 8] = _kart_blk(ord_i)
        raw[KART_ORD] = ord_i & 0xFF
        rec.raw = bytes(raw)
    new_pos = _channel_positions(list(zip(indices, desired_channels)))
    return {old_pos[ch]: new_pos[ch] for ch in by_ch}


def _remap_arrange_placements(pd: ProjectData, pos_map: dict[int, int]) -> None:
    if not pos_map:
        return
    aq = ProjectData._arrange_audio_evsq(pd.records)
    if aq is None:
        return
    raw = pd.records[aq].raw
    body = bytearray(raw[REC_HEADER_SIZE : REC_HEADER_SIZE + _u32(raw, REC_SIZE_OFF)])
    o = 0
    while o + ProjectData.PLACEMENT_EVENT_SIZE <= len(body):
        tag = _u32(body, o)
        if tag in (0x20, 0x24):
            old = body[o + ProjectData.PLACEMENT_TRACK_OFF]
            if old in pos_map:
                body[o + ProjectData.PLACEMENT_TRACK_OFF] = pos_map[old] & 0xFF
        o += 4
    nh = bytearray(raw[:REC_HEADER_SIZE])
    struct.pack_into("<I", nh, REC_SIZE_OFF, len(body))
    pd.records[aq].raw = bytes(nh) + bytes(body)


def _refresh_arrange_tables(pd: ProjectData, track_count: int) -> None:
    """Update arrange-order rows and track-area height after reorder."""
    n = track_count
    r = next((rr for rr in pd.records if rr.tag == b"qSvE" and _u32(rr.raw, 0x08) == ARR_ORDER_IDX), None)
    if r is not None:
        b = bytearray(r.raw)
        k = 0
        while ARR_ORDER_ROW0 + k * 0x50 < len(b):
            o = ARR_ORDER_ROW0 + k * 0x50
            b[o] = 0x43 if k == 0 else ((0x40 - n + k) & 0xFF if k <= n else (k - n) & 0xFF)
            k += 1
        r.raw = bytes(b)
    rec = _arrange_container(pd.records)
    if rec is not None:
        off = _arr_height_off(rec.raw)
        if off + 2 <= len(rec.raw):
            b = bytearray(rec.raw)
            struct.pack_into("<H", b, off, (ARR_ROW_H * (n + 1)) & 0xFFFF)
            rec.raw = bytes(b)


def apply_track_order(logicx_dir, project: Project, report) -> None:
    """Place exported regions on synthesized tracks and match interleaved source order."""
    from pathlib import Path

    pd_path = Path(logicx_dir) / "Alternatives" / "000" / "ProjectData"
    pd = ProjectData.parse(pd_path.read_bytes())

    export_channels = export_channel_order(pd, project)
    prefix = _template_prefix_channels(pd)
    desired = prefix + export_channels

    rows = _arrange_row_channels(pd)
    current = [ch for _, ch in rows]
    if current != desired:
        pos_map = _reorder_arrange_rows(pd, desired)
        _remap_arrange_placements(pd, pos_map)
        _refresh_arrange_tables(pd, len(desired))
        if is_interleaved(project):
            report.warnings.append(
                "reordered Logic arrange tracks to match interleaved DAWproject track order"
            )

    pd_path.write_bytes(pd.serialize())
