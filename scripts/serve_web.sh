#!/usr/bin/env bash
# Serve the static web UI locally (requires a built web/wasm/daw2logic.wasm).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${1:-8080}"
if [[ ! -f "$ROOT/web/wasm/daw2logic.wasm" ]]; then
  echo "Missing web/wasm/daw2logic.wasm — run scripts/build_wasm.sh first" >&2
  exit 1
fi
if [[ ! -f "$ROOT/web/coi-serviceworker.js" ]]; then
  curl -fsSL \
    https://raw.githubusercontent.com/gzuidhof/coi-serviceworker/master/coi-serviceworker.min.js \
    -o "$ROOT/web/coi-serviceworker.js"
fi
echo "Serving $ROOT/web at http://localhost:$PORT"
exec python3 -m http.server "$PORT" --directory "$ROOT/web"
