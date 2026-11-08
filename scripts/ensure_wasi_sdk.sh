#!/usr/bin/env bash
# Ensure Nuitka's wasi-sdk/21/sdk-$OS tree exists (with retries).
# Avoids bare requests.get() 504s from nuitka.utils.wasi_sdk.download_sdk().
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv-wasm}"
WASI_SDK_VERSION="${WASI_SDK_VERSION:-21}"
WASI_SDK_RELEASE="${WASI_SDK_RELEASE:-21.0}"

# shellcheck disable=SC1091
source "$VENV/bin/activate"

NUITKA="$(python -c 'import nuitka, pathlib; print(pathlib.Path(nuitka.__file__).parent)')"
SDK_ROOT="$NUITKA/wasi-sdk/${WASI_SDK_VERSION}"

OS_NAME="$(python -c 'import platform; print(platform.system())')"
case "$OS_NAME" in
  Linux)  ARCHIVE="wasi-sdk-${WASI_SDK_RELEASE}-linux.tar.gz" ;;
  Darwin) ARCHIVE="wasi-sdk-${WASI_SDK_RELEASE}-macos.tar.gz" ;;
  Windows) ARCHIVE="wasi-sdk-${WASI_SDK_RELEASE}.m-mingw.tar.gz" ;;
  *)
    echo "unsupported OS for wasi-sdk: $OS_NAME" >&2
    exit 1
    ;;
esac

SDK_DIR="$SDK_ROOT/sdk-$OS_NAME"
CLANG="$SDK_DIR/bin/clang"
if [[ -x "$CLANG" ]]; then
  echo "==> Using existing wasi-sdk at $SDK_DIR"
  echo "$SDK_DIR"
  exit 0
fi

mkdir -p "$SDK_ROOT"
ARCHIVE_PATH="$SDK_ROOT/$ARCHIVE"
URL="https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-${WASI_SDK_VERSION}/$ARCHIVE"

fetch_with_retries() {
  local url=$1 dest=$2
  local attempt
  for attempt in 1 2 3 4 5; do
    echo "==> Downloading wasi-sdk (attempt $attempt/5): $url"
    if curl -fL --retry 5 --retry-all-errors --retry-delay 3 \
      --connect-timeout 30 --max-time 600 \
      -o "$dest.partial" "$url"; then
      mv "$dest.partial" "$dest"
      return 0
    fi
    rm -f "$dest.partial"
    sleep $((attempt * 2))
  done
  echo "failed to download wasi-sdk after retries: $url" >&2
  return 1
}

if [[ ! -f "$ARCHIVE_PATH" ]]; then
  fetch_with_retries "$URL" "$ARCHIVE_PATH"
fi

echo "==> Extracting $ARCHIVE"
rm -rf "$SDK_DIR" "$SDK_ROOT/_extract"
mkdir -p "$SDK_ROOT/_extract"
tar -xzf "$ARCHIVE_PATH" -C "$SDK_ROOT/_extract"
EXTRACTED="$(find "$SDK_ROOT/_extract" -mindepth 1 -maxdepth 1 -type d | head -1)"
if [[ -z "$EXTRACTED" ]]; then
  echo "wasi-sdk archive extracted nothing usable" >&2
  exit 1
fi
mv "$EXTRACTED" "$SDK_DIR"
rm -rf "$SDK_ROOT/_extract"

if [[ ! -x "$CLANG" ]]; then
  echo "wasi clang missing after extract: $CLANG" >&2
  exit 1
fi

echo "==> wasi-sdk ready at $SDK_DIR"
echo "$SDK_DIR"
