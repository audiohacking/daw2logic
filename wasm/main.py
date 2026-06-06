#!/usr/bin/env python3
"""WASI entry point: read .dawproject zip from stdin, write framed result to stdout."""

# py2wasm / Nuitka module options (see Nuitka user manual — "nuitka-project" lines)
# py2wasm compiles this file; these lines pull in the full converter tree + Logic seeds.
# nuitka-project: --include-package=daw2logic
# nuitka-project: --include-package=logicx
# nuitka-project: --include-package-data=logicx
# nuitka-project: --include-module=zlib
# nuitka-project: --nofollow-import-to=pytest
# nuitka-project: --nofollow-import-to=tests

from __future__ import annotations

import sys
import zlib  # noqa: F401 — Nuitka anti-bloat omits zlib unless forced; zipfile needs it

from daw2logic.wasm_api import convert_dawproject_bytes, pack_conversion_result


def main() -> int:
    data = sys.stdin.buffer.read()
    if not data:
        print("error: empty stdin (expected .dawproject zip bytes)", file=sys.stderr)
        return 1
    try:
        logicx_zip, notes = convert_dawproject_bytes(data)
        sys.stdout.buffer.write(pack_conversion_result(logicx_zip, notes))
        sys.stdout.buffer.flush()
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
