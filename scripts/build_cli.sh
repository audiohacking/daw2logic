#!/usr/bin/env bash
# Build a standalone daw2logic CLI executable with PyInstaller.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${DIST:-$ROOT/dist}"
VENV="${VENV:-$ROOT/.venv-release}"
PY="${PY:-python3.11}"
NAME="${NAME:-daw2logic}"

if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi

case "$(uname -s)" in
  Linux)  ASSET="${ASSET:-daw2logic-linux-x86_64}" ;;
  Darwin)
    case "$(uname -m)" in
      arm64) ASSET="${ASSET:-daw2logic-macos-arm64}" ;;
      *)     ASSET="${ASSET:-daw2logic-macos-x86_64}" ;;
    esac
    ;;
  *)
    echo "unsupported OS: $(uname -s)" >&2
    exit 1
    ;;
esac

if [[ ! -d "$VENV" ]]; then
  echo "==> Creating venv at $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "==> Installing build deps"
pip install -q --upgrade pip
pip install -q pyinstaller
pip install -q -e "$ROOT/third_party/LogicProFormatWriter"
pip install -q -e "$ROOT"

mkdir -p "$DIST"
SPEC="$ROOT/$NAME.spec"
rm -f "$SPEC"

echo "==> Building $ASSET"
pyinstaller --noconfirm --clean --onefile \
  --name "$NAME" \
  --distpath "$DIST" \
  --workpath "$ROOT/build/pyinstaller" \
  --specpath "$ROOT/build/pyinstaller" \
  --collect-data logicx \
  --collect-submodules daw2logic \
  --paths "$ROOT" \
  --paths "$ROOT/third_party/LogicProFormatWriter" \
  "$ROOT/scripts/cli_entry.py"

mv "$DIST/$NAME" "$DIST/$ASSET"
chmod +x "$DIST/$ASSET"

echo "==> Built $(du -h "$DIST/$ASSET" | awk '{print $1}') $DIST/$ASSET"

if [[ -f "$ROOT/tests/fixtures/bitwig_simple.dawproject" ]]; then
  echo "==> Smoke test"
  "$DIST/$ASSET" "$ROOT/tests/fixtures/bitwig_simple.dawproject" -o /tmp/daw2logic-cli-smoke.logicx --force
  test -d /tmp/daw2logic-cli-smoke.logicx
  echo "CLI smoke test OK"
fi
