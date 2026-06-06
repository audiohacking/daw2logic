#!/usr/bin/env python3
"""Build tests/fixtures/*.dawproject archives."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent
WAV = ROOT / "third_party" / "dawproject" / "test-data" / "white-glasses.wav"
AU_PRESET = ROOT / "third_party" / "LogicFiles" / "Tests" / "Resources" / "PP.aupreset"


def _write(name: str, src_dir: Path, *, extra: dict[str, Path] | None = None) -> Path:
    out = FIXTURES / name
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(src_dir / "project.xml", "project.xml")
        zf.write(src_dir / "metadata.xml", "metadata.xml")
        zf.write(WAV, "audio/white-glasses.wav")
        for arc, src in (extra or {}).items():
            zf.write(src, arc)
    return out


def build_all() -> list[Path]:
    if not WAV.is_file():
        raise SystemExit(f"missing audio fixture: {WAV} (init submodules)")
    paths = [
        _write("bitwig_simple.dawproject", FIXTURES / "bitwig_simple"),
        _write("bitwig_extended.dawproject", FIXTURES / "bitwig_extended"),
    ]
    if AU_PRESET.is_file():
        paths.append(
            _write(
                "bitwig_au.dawproject",
                FIXTURES / "bitwig_au",
                extra={"plugins/demo.aupreset": AU_PRESET},
            )
        )
    return paths


if __name__ == "__main__":
    for path in build_all():
        print(f"wrote {path}")
