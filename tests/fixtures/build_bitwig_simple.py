#!/usr/bin/env python3
"""Build tests/fixtures/*.dawproject archives."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent
WAV = ROOT / "third_party" / "dawproject" / "test-data" / "white-glasses.wav"


def _write(name: str, src_dir: Path) -> Path:
    out = FIXTURES / name
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_dir / "project.xml", "project.xml")
        zf.write(src_dir / "metadata.xml", "metadata.xml")
        zf.write(WAV, "audio/white-glasses.wav")
    return out


def build_all() -> list[Path]:
    if not WAV.is_file():
        raise SystemExit(f"missing audio fixture: {WAV} (init submodules)")
    return [
        _write("bitwig_simple.dawproject", FIXTURES / "bitwig_simple"),
        _write("bitwig_extended.dawproject", FIXTURES / "bitwig_extended"),
    ]


if __name__ == "__main__":
    for path in build_all():
        print(f"wrote {path}")
