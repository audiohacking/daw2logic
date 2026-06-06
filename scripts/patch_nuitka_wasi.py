#!/usr/bin/env python3
"""Patch Nuitka MetaPathBasedLoader for WASI static extension imports."""

from __future__ import annotations

import pathlib
import sys

CALLINTO_MARKER = "wasi static extension via PyInit_zlib"

CALLINTO_OLD = """#ifdef __wasi__
    const char *error = "dynamic libraries are not implemented in wasi";
    SET_CURRENT_EXCEPTION_TYPE0_STR(tstate, PyExc_ImportError, error);
    return NULL;

    entrypoint_t entrypoint = NULL;
#else"""

CALLINTO_NEW = f"""#ifdef __wasi__
    if (isVerbose()) {{
        PySys_WriteStderr("import %s # {CALLINTO_MARKER}\\n", full_name);
    }}

    entrypoint_t entrypoint = NULL;
    if (strcmp(entry_function_name, "PyInit_zlib") == 0) {{
        extern PyObject *PyInit_zlib(void);
        entrypoint = (entrypoint_t)PyInit_zlib;
    }}

    if (unlikely(entrypoint == NULL)) {{
        SET_CURRENT_EXCEPTION_TYPE0_STR(tstate, PyExc_ImportError, "static extension not linked");
        return NULL;
    }}
#else"""

LEGACY_MARKERS = (
    CALLINTO_MARKER,
    "wasi static extension via dlsym",
    "wasi loadModule create_builtin exec_builtin",
    "wasi create_module create_builtin built-in",
    "wasi exec_module exec_builtin",
    "wasi find_spec skip extension modules",
    "wasi find_spec delegate extension to BuiltinImporter",
    "wasi loadModule create_builtin",
    "wasi static extension via _imp.create_builtin",
    "daw2logic zlib inittab",
)


def main() -> int:
    import nuitka

    loader_path = pathlib.Path(nuitka.__file__).parent / "build/static_src/MetaPathBasedLoader.c"
    text = loader_path.read_text()

    if CALLINTO_MARKER in text:
        print(f"already patched: {loader_path}")
        return 0

    if any(m in text for m in LEGACY_MARKERS):
        print(
            "legacy WASI patch detected; reinstall py2wasm fork first:\n"
            "  pip install --force-reinstall --no-deps "
            "'py2wasm @ git+https://github.com/lum1n0us/Nuitka@dev/wasi_sync_upstream'",
            file=sys.stderr,
        )
        return 1

    if CALLINTO_OLD not in text:
        print(f"callIntoExtensionModule patch target not found in {loader_path}", file=sys.stderr)
        return 1

    loader_path.write_text(text.replace(CALLINTO_OLD, CALLINTO_NEW, 1))
    print(f"patched: {loader_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
