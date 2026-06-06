#!/usr/bin/env python3
"""Build tests/fixtures/bitwig_simple.dawproject from source XML + dawproject test WAV."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(__file__).resolve().parent / "bitwig_simple"
OUT = Path(__file__).resolve().parent / "bitwig_simple.dawproject"
WAV = ROOT / "third_party" / "dawproject" / "test-data" / "white-glasses.wav"


def build() -> Path:
    if not WAV.is_file():
        raise SystemExit(f"missing audio fixture: {WAV} (init submodules)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(SRC / "project.xml", "project.xml")
        zf.write(SRC / "metadata.xml", "metadata.xml")
        zf.write(WAV, "audio/white-glasses.wav")
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path}")
