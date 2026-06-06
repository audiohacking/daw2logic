"""In-memory conversion API for WASM / browser hosts."""

from __future__ import annotations

import io
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from . import parser
from .convert import convert, format_conversion_notes

def _zip_logicx_bundle(bundle_dir: Path) -> bytes:
    """Zip a .logicx bundle directory for browser download.

    WASI temp files often report mtime 0; use conversion time instead of st_mtime.
    """
    zip_time = time.gmtime()[:6]  # type: ignore[assignment]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(bundle_dir.rglob("*")):
            if not file_path.is_file():
                continue
            arcname = file_path.relative_to(bundle_dir).as_posix()
            info = zipfile.ZipInfo(arcname)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.date_time = zip_time
            zf.writestr(info, file_path.read_bytes())
    return buf.getvalue()


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

        buf = _zip_logicx_bundle(out_path)
        return buf, notes


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
