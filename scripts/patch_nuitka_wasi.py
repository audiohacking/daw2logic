#!/usr/bin/env python3
"""Patch Nuitka MetaPathBasedLoader for WASI static extension imports."""

from __future__ import annotations

import pathlib
import sys

MARKER = "wasi static extension via _imp.create_builtin"

OLD = """#ifdef __wasi__
    const char *error = "dynamic libraries are not implemented in wasi";
    SET_CURRENT_EXCEPTION_TYPE0_STR(tstate, PyExc_ImportError, error);
    return NULL;

    entrypoint_t entrypoint = NULL;
#else"""

NEW = f"""#ifdef __wasi__
    if (isVerbose()) {{
        PySys_WriteStderr("import %s # {MARKER}\\n", full_name);
    }}

    PyObject *imp_module = PyImport_ImportModule("_imp");
    if (unlikely(imp_module == NULL)) {{
        return NULL;
    }}

    PyObject *create_builtin = PyObject_GetAttrString(imp_module, "create_builtin");
    Py_DECREF(imp_module);

    if (unlikely(create_builtin == NULL)) {{
        return NULL;
    }}

    PyObject *basename_obj = Nuitka_String_FromString(name);
    PyObject *static_module = PyObject_CallFunctionObjArgs(create_builtin, basename_obj, NULL);
    Py_DECREF(basename_obj);
    Py_DECREF(create_builtin);

    PGO_onModuleEntered(full_name);
    PGO_onModuleExit(name, static_module == NULL);

    if (unlikely(static_module == NULL)) {{
        return NULL;
    }}

    {{
        PyObject *full_name_obj = Nuitka_String_FromString(full_name);
        Nuitka_SetModule(full_name_obj, static_module);
        Py_DECREF(full_name_obj);
    }}

    return static_module;

    entrypoint_t entrypoint = NULL;
#else"""


def main() -> int:
    import nuitka

    path = pathlib.Path(nuitka.__file__).parent / "build/static_src/MetaPathBasedLoader.c"
    text = path.read_text()
    if MARKER in text:
        print(f"already patched: {path}")
        return 0
    if OLD not in text:
        print(f"patch target not found in {path}", file=sys.stderr)
        return 1
    path.write_text(text.replace(OLD, NEW, 1))
    print(f"patched: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
