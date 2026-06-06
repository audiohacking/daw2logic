"""Parse Logic / DAWproject AU preset (.aupreset) plists."""

from __future__ import annotations

import plistlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AupresetInfo:
    name: str | None
    manufacturer: int | None
    subtype: int | None
    au_type: int | None
    version: int | None
    payload_size: int


def _fourcc(value: int | None) -> str | None:
    if value is None:
        return None
    return value.to_bytes(4, "big", signed=True).decode("latin-1", "replace")


def read_aupreset(path: Path) -> AupresetInfo:
    data = plistlib.loads(path.read_bytes())
    if not isinstance(data, dict):
        raise ValueError(f"not an aupreset plist dict: {path}")
    payload = data.get("data") or b""
    if isinstance(payload, memoryview):
        payload = payload.tobytes()
    return AupresetInfo(
        name=data.get("name"),
        manufacturer=data.get("manufacturer"),
        subtype=data.get("subtype"),
        au_type=data.get("type"),
        version=data.get("version"),
        payload_size=len(payload) if isinstance(payload, (bytes, bytearray)) else 0,
    )


def component_summary(info: AupresetInfo) -> str:
    parts = [
        _fourcc(info.manufacturer),
        _fourcc(info.au_type),
        _fourcc(info.subtype),
    ]
    return ":".join(p for p in parts if p)
