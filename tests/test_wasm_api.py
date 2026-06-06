"""Tests for the in-memory WASM conversion API."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from daw2logic.wasm_api import (
    convert_dawproject_bytes,
    pack_conversion_result,
    unpack_conversion_result,
)


def test_convert_bitwig_simple_roundtrip(tmp_path):
    src = Path("tests/fixtures/bitwig_simple.dawproject")
    if not src.is_file():
        pytest.skip("run tests/fixtures/build_bitwig_simple.py first")
    logicx_zip, notes = convert_dawproject_bytes(src.read_bytes(), source_name="bitwig_simple.dawproject")
    assert "daw2logic conversion notes" in notes
    assert "1 instrument track(s)" in notes

    wire = pack_conversion_result(logicx_zip, notes)
    out_zip, out_notes = unpack_conversion_result(wire)
    assert out_notes == notes
    assert out_zip == logicx_zip

    with zipfile.ZipFile(io.BytesIO(logicx_zip)) as zf:
        names = zf.namelist()
    assert any("Alternatives/000/ProjectData" in n for n in names)
