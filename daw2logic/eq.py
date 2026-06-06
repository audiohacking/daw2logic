"""DAWproject Equalizer → Logic Channel EQ mapping."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from .ir import EqBand, EqualizerInfo

# Logic Channel EQ band types (user-facing names).
LOGIC_EQ_TYPES = {
    "highPass": "low_cut",
    "lowPass": "low_cut",
    "bandPass": "parametric",
    "bell": "parametric",
    "notch": "parametric",
    "lowShelf": "low_shelf",
    "highShelf": "high_shelf",
}


def semitones_to_hz(semitones: float) -> float:
    """DAWproject EQ Freq unit=semitones uses absolute pitch (69 = A4 = 440 Hz)."""
    return 440.0 * (2.0 ** ((semitones - 69.0) / 12.0))


def _param_value(el: ET.Element | None, tag: str) -> float | None:
    if el is None:
        return None
    child = el.find(tag)
    if child is None:
        return None
    raw = child.get("value")
    return float(raw) if raw is not None else None


def _param_bool(el: ET.Element | None, tag: str) -> bool | None:
    if el is None:
        return None
    child = el.find(tag)
    if child is None:
        return None
    raw = child.get("value")
    if raw is None:
        return None
    return raw.lower() in {"true", "1"}


def parse_equalizer(el: ET.Element) -> EqualizerInfo:
    bands: list[EqBand] = []
    for band_el in el.findall("Band"):
        freq_semi = _param_value(band_el, "Freq")
        bands.append(
            EqBand(
                band_type=band_el.get("type") or "bell",
                frequency_hz=semitones_to_hz(freq_semi) if freq_semi is not None else None,
                frequency_semitones=freq_semi,
                gain_db=_param_value(band_el, "Gain"),
                q=_param_value(band_el, "Q"),
                enabled=_param_bool(band_el, "Enabled"),
                order=int(band_el.get("order")) if band_el.get("order") else None,
            )
        )
    enabled = _param_bool(el, "Enabled")
    return EqualizerInfo(
        name=el.get("deviceName") or el.get("name"),
        device_id=el.get("deviceID"),
        enabled=enabled if enabled is not None else True,
        bands=tuple(bands),
        input_gain_db=_param_value(el, "InputGain"),
        output_gain_db=_param_value(el, "OutputGain"),
    )


def equalizer_to_logic_channel_eq(eq: EqualizerInfo) -> dict:
    """Sidecar payload for Logic's stock Channel EQ (manual or future native graft)."""
    return {
        "target_plugin": "Logic Channel EQ",
        "enabled": eq.enabled,
        "input_gain_db": eq.input_gain_db,
        "output_gain_db": eq.output_gain_db,
        "bands": [
            {
                "logic_type": LOGIC_EQ_TYPES.get(b.band_type, "parametric"),
                "dawproject_type": b.band_type,
                "frequency_hz": b.frequency_hz,
                "gain_db": b.gain_db,
                "q": b.q,
                "enabled": b.enabled,
            }
            for b in eq.bands
        ],
    }
