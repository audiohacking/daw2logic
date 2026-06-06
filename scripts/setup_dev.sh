#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

git submodule update --init --recursive

python3 -m pip install -e third_party/LogicProFormatWriter
python3 -m pip install -e ".[dev]"

python3 tests/fixtures/build_bitwig_simple.py
echo "ready — run: pytest"
