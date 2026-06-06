#!/usr/bin/env bash
# Compile CPython zlibmodule + libz objects for wasm32-wasi linking.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv-wasm}"
OUT="${WASI_ZLIB_OUT:-$ROOT/tmp/wasi-zlib}"
CPYTHON_TAG="${CPYTHON_TAG:-v3.11.9}"
ZLIB_VERSION="${ZLIB_VERSION:-1.3.1}"

# shellcheck disable=SC1091
source "$VENV/bin/activate"

NUITKA="$(python -c 'import nuitka, pathlib; print(pathlib.Path(nuitka.__file__).parent)')"
WASI_SDK="$(python - <<'PY'
import contextlib
import os
import platform
import sys

import nuitka

sdk = os.path.join(
    os.path.dirname(nuitka.__file__),
    f"wasi-sdk/21/sdk-{platform.system()}",
)
clang = os.path.join(sdk, "bin/clang")
if not os.path.isfile(clang):
    from nuitka.utils.wasi_sdk import download_sdk

    with contextlib.redirect_stdout(sys.stderr):
        download_sdk()

print(sdk)
PY
)"
CLANG="$WASI_SDK/bin/clang"
SYSROOT="$WASI_SDK/share/wasi-sysroot"

if [[ ! -x "$CLANG" ]]; then
  echo "wasi clang not found at $CLANG" >&2
  exit 1
fi

mkdir -p "$OUT" "$OUT/clinic" "$OUT/zlib-src"

fetch() {
  local url=$1 dest=$2
  if [[ ! -f "$dest" ]]; then
    curl -fsSL "$url" -o "$dest"
  fi
}

fetch "https://raw.githubusercontent.com/python/cpython/${CPYTHON_TAG}/Modules/zlibmodule.c" \
  "$OUT/zlibmodule.c"
fetch "https://raw.githubusercontent.com/python/cpython/${CPYTHON_TAG}/Modules/clinic/zlibmodule.c.h" \
  "$OUT/clinic/zlibmodule.c.h"

if [[ ! -f "$OUT/zlib-src/zutil.c" ]]; then
  curl -fsSL "https://zlib.net/fossils/zlib-${ZLIB_VERSION}.tar.gz" | tar xz -C "$OUT/zlib-src" --strip-components=1
fi

WASI_CFLAGS=(
  --target=wasm32-wasi
  --sysroot="$SYSROOT"
  -D_WASI_EMULATED_MMAN
  -D_WASI_EMULATED_GETPID
  -D_WASI_EMULATED_SIGNAL
  -D_WASI_EMULATED_PROCESS_CLOCKS
  -O2
  -DPy_NO_ENABLE_SHARED
  -w
)

echo "==> Compiling libz for wasm32-wasi"
for src in adler32 compress deflate infback inffast inflate inftrees trees zutil; do
  "$CLANG" -c -o "$OUT/libz_${src}.o" "$OUT/zlib-src/${src}.c" \
    "${WASI_CFLAGS[@]}" -I"$OUT/zlib-src"
done
# crc32 is already compiled via Nuitka's inline_copy/zlib/crc32.c — skip libz crc32.o.

echo "==> Compiling zlibmodule.c for wasm32-wasi"
"$CLANG" -c -o "$OUT/zlibmodule.o" "$OUT/zlibmodule.c" \
  "${WASI_CFLAGS[@]}" \
  -I"$NUITKA/build/inline_copy/zlib" \
  -I"$NUITKA/wasi-python/include/python3.11" \
  -I"$NUITKA/wasi-python/include/python3.11/internal" \
  -I"$OUT"

OBJECTS=("$OUT/zlibmodule.o" "$OUT"/libz_*.o)
printf '%s\n' "${OBJECTS[@]}" > "$OUT/objects.txt"
echo "==> WASI zlib objects ready (${#OBJECTS[@]} files)"
