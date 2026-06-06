"""In-memory conversion API for WASM / browser hosts."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from . import parser
from .convert import convert, format_conversion_notes


def convert_dawproject_bytes(
    data: bytes,
    *,
    source_name: str = "upload.dawproject",
) -> tuple[bytes, str]:
    """Convert a .dawproject zip archive to a zipped .logicx bundle + notes text."""
    if not data:
        raise ValueError("empty input")
    with TemporaryDirectory(prefix="daw2logic-in-") as in_root, TemporaryDirectory(
        prefix="daw2logic-out-"
    ) as out_root:
        daw_path = Path(in_root) / source_name
        daw_path.write_bytes(data)
        project = parser.load(daw_path)
        try:
            out_path = Path(out_root) / "output.logicx"
            report = convert(project, out_path)
            notes = format_conversion_notes(
                report,
                source=source_name,
                output="output.logicx",
            )
        finally:
            parser.cleanup(project)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in sorted(out_path.rglob("*")):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(out_path).as_posix())
        return buf.getvalue(), notes


def pack_conversion_result(logicx_zip: bytes, notes: str) -> bytes:
    """Length-prefixed wire format: u32 notes_len, u32 zip_len, notes, zip."""
    import struct

    notes_bytes = notes.encode("utf-8")
    return struct.pack("<II", len(notes_bytes), len(logicx_zip)) + notes_bytes + logicx_zip


def unpack_conversion_result(payload: bytes) -> tuple[bytes, str]:
    """Inverse of :func:`pack_conversion_result`."""
    import struct

    if len(payload) < 8:
        raise ValueError("truncated conversion result")
    notes_len, zip_len = struct.unpack_from("<II", payload, 0)
    end = 8 + notes_len + zip_len
    if end != len(payload):
        raise ValueError("conversion result length mismatch")
    notes = payload[8 : 8 + notes_len].decode("utf-8")
    logicx_zip = payload[8 + notes_len : end]
    return logicx_zip, notes
