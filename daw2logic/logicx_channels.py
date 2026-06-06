"""Map daw2logic tracks to Logic Pro environment channel indices."""

from __future__ import annotations

from logicx.projectdata import (
    KART_BASE_CHAN,
    KART_CHAN,
    KART_MASTER_CHAN,
    ProjectData,
    _is_instrument_ivne,
)


def _arrange_channel_order(pd: ProjectData) -> list[int]:
    """Environment channel idx values in arrange-track stream order (excludes master)."""
    channels: list[int] = []
    for r in pd.records:
        if r.tag != b"karT" or len(r.raw) != 93:
            continue
        if int.from_bytes(r.raw[0x08:0x0C], "little") != 0x040000:
            continue
        ch = int.from_bytes(r.raw[KART_CHAN:KART_CHAN + 4], "little")
        if ch == KART_MASTER_CHAN:
            continue
        channels.append(ch)
    return channels


def instrument_channels(pd: ProjectData) -> dict[int, int]:
    """{1-based instrument ordinal: environment channel idx}."""
    out: dict[int, int] = {}
    n = 0
    for ch in _arrange_channel_order(pd):
        iv = next((x for x in pd.records if x.tag == b"ivnE" and int.from_bytes(x.raw[0x08:0x0C], "little") == ch), None)
        if iv is not None and _is_instrument_ivne(pd, iv):
            n += 1
            out[n] = ch
    return out


def audio_channels(pd: ProjectData) -> dict[int, int]:
    """{1-based audio ordinal: environment channel idx}."""
    out: dict[int, int] = {}
    n = 0
    for ch in _arrange_channel_order(pd):
        iv = next((x for x in pd.records if x.tag == b"ivnE" and int.from_bytes(x.raw[0x08:0x0C], "little") == ch), None)
        if iv is not None and not _is_instrument_ivne(pd, iv):
            n += 1
            out[n] = ch
    return out


def channel_for_track(
    pd: ProjectData,
    *,
    has_midi: bool,
    inst_ordinal: int | None,
    aud_ordinal: int | None,
) -> int | None:
    """Resolve the environment channel for one exported track."""
    if has_midi and inst_ordinal is not None:
        return instrument_channels(pd).get(inst_ordinal)
    if aud_ordinal is not None:
        return audio_channels(pd).get(aud_ordinal)
    return None
