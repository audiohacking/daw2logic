#!/usr/bin/env bash
# Compile wasm/main.py to web/wasm/daw2logic.wasm using the Wasmer py2wasm (Nuitka WASI) fork.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/web/wasm/daw2logic.wasm"
VENV="${VENV:-$ROOT/.venv-wasm}"
PY="${PY:-python3.11}"

if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi

echo "==> Using Python: $($PY --version)"

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating venv at $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Installing py2wasm fork + project deps"
pip install -q --upgrade pip
pip install -q "py2wasm @ git+https://github.com/lum1n0us/Nuitka@dev/wasi_sync_upstream"
pip install -q -e "$ROOT/third_party/LogicProFormatWriter"
pip install -q -e "$ROOT"

apply_nuitka_wasi_patch() {
  echo "==> Patching Nuitka for WASI static extension imports"
  python "$ROOT/scripts/patch_nuitka_wasi.py"
}

LIBATOMIC=""
if command -v gcc >/dev/null 2>&1; then
  LIBATOMIC="$(gcc -print-search-dirs 2>/dev/null | awk '/^install:/ {print $2}' | head -1 || true)"
fi
export LDFLAGS="${LDFLAGS:-${LIBATOMIC:+-L$LIBATOMIC}}"

mkdir -p "$(dirname "$OUT")"

apply_nuitka_wasi_patch

echo "==> Compiling wasm/main.py -> $OUT"
py2wasm "$ROOT/wasm/main.py" -o "$OUT"

echo "==> Built $(du -h "$OUT" | awk '{print $1}') wasm module"

if command -v wasmer >/dev/null 2>&1; then
  FIXTURE="$ROOT/tests/fixtures/bitwig_simple.dawproject"
  if [[ -f "$FIXTURE" ]]; then
    echo "==> Smoke test with wasmer"
    wasmer run "$OUT" < "$FIXTURE" > /tmp/daw2logic-smoke.out
    "$PY" - <<'PY'
import struct, zipfile, io, sys
raw = open("/tmp/daw2logic-smoke.out", "rb").read()
notes_len, zip_len = struct.unpack_from("<II", raw, 0)
notes = raw[8:8+notes_len].decode()
zip_bytes = raw[8+notes_len:8+notes_len+zip_len]
assert "daw2logic conversion notes" in notes
with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
    assert any("ProjectData" in n for n in zf.namelist())
print("wasmer smoke test OK")
PY
  fi
else
  echo "==> wasmer CLI not installed; skipping smoke test"
fi
