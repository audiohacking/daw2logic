"""Map DAWproject #rrggbb colors to Logic palette indices (RE in progress)."""

from __future__ import annotations

import math
import re
import struct

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")

# Logic-validated 2026-06 (color_changed.logicx): picker index @ qeSM+0x2d, u32 @ +0x2c.
QESM_2C_BY_PICKER: dict[int, int] = {
    4: 0xCE,  # Drumloop red
    6: 0x6D,  # Bass orange
}
QESM_DEFAULT_2C_BY_CHANNEL_SUFFIX = {
    0x00: 0x22,  # Bass 0x600000
    0x04: 0x23,  # Drumloop 0x640000 — channel & 0xff
}


def parse_hex_color(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    m = _HEX.match(value.strip())
    if not m:
        return None
    raw = m.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _dist2(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


# Logic color-picker indices (approx RGB) + RE capture anchors.
LOGIC_PICKER_COLORS: tuple[tuple[int, tuple[int, int, int]], ...] = (
    (1, (180, 40, 45)),
    (2, (255, 55, 50)),
    (3, (255, 100, 45)),
    (4, (255, 60, 55)),      # validated red
    (5, (255, 150, 40)),
    (6, (255, 150, 50)),     # validated orange
    (7, (255, 200, 50)),
    (8, (200, 220, 60)),
    (9, (120, 200, 70)),
    (10, (0, 170, 80)),
    (11, (0, 160, 130)),
    (12, (0, 150, 200)),
    (13, (50, 90, 200)),
    (14, (100, 70, 190)),
    (15, (160, 50, 180)),
    (16, (200, 50, 140)),
    (17, (220, 60, 100)),
    (18, (200, 90, 80)),
    (19, (160, 100, 70)),
    (20, (120, 90, 60)),
    (21, (90, 90, 90)),
    (22, (130, 130, 130)),
    (23, (170, 170, 170)),
    (24, (210, 210, 210)),
    (29, (87, 97, 198)),
    (31, (132, 138, 224)),
    (33, (149, 73, 203)),
    (35, (217, 56, 113)),
    (37, (217, 46, 36)),
    (39, (217, 157, 16)),
    (41, (255, 87, 6)),
    (47, (0, 157, 71)),      # ~#009d47 green (RE capture)
)


def nearest_logic_picker_index(hex_color: str | None) -> int | None:
    rgb = parse_hex_color(hex_color)
    if rgb is None:
        return None
    best_idx, best_d = None, math.inf
    for idx, pal in LOGIC_PICKER_COLORS:
        d = _dist2(rgb, pal)
        if d < best_d:
            best_d = d
            best_idx = idx
    return best_idx


def _default_qesm_2c(channel: int) -> int:
    slot = channel & 0xFF
    return QESM_DEFAULT_2C_BY_CHANNEL_SUFFIX.get(slot, 0x22)


def _default_qesm_aux(channel: int) -> int:
    # Baseline: Bass 0xa8 @0x600000, Drumloop 0xac @0x640000 (+4 per slot step).
    base = 0xA8
    slot = (channel - 0x600000) // 0x40000 if channel >= 0x600000 else 0
    return (base + 4 * slot) & 0xFF


def qesm_track_color_bytes(picker_index: int, channel: int) -> tuple[int, int]:
    """Return (u32 @+0x2c, byte @+0x10e) for a Logic track color picker index."""
    byte_2c = QESM_2C_BY_PICKER.get(picker_index, _default_qesm_2c(channel) + picker_index)
    u32 = byte_2c | (picker_index << 8)
    aux = (_default_qesm_aux(channel) - 8) & 0xFF
    return u32, aux


def region_color_bytes(hex_color: str) -> bytes:
    """8-byte gRuA @+0x4e blob for a custom region color."""
    picker = nearest_logic_picker_index(hex_color) or 0
    # Validated custom region (green) from color_changed.logicx first gRuA.
    blob = bytearray.fromhex("62f0b39a1bff61ff")
    blob[7] = picker & 0xFF
    return bytes(blob)


def color_sidecar_entry(hex_color: str | None) -> dict | None:
    rgb = parse_hex_color(hex_color)
    if rgb is None:
        return None
    idx = nearest_logic_picker_index(hex_color)
    return {
        "hex": hex_color if hex_color.startswith("#") else f"#{hex_color}",
        "rgb": list(rgb),
        "logic_palette_index": idx,
    }
