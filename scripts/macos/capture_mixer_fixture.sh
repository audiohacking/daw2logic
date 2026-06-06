#!/usr/bin/env bash
# Capture an OCuA mixer differential fixture using Logic Pro (macOS, manual fader step).
#
# Prerequisite: grant Terminal/Cursor "Accessibility" in System Settings if you automate
# the fader later; this script only opens Logic and diffs after you move one fader.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

baseline="$work/re.logicx"
after="$work/re_vol.logicx"

if [[ ! -d "$baseline/Alternatives/000" ]]; then
  echo "building baseline at $baseline"
  (cd "$root" && PYTHONPATH="third_party/LogicProFormatWriter:." python3 -m daw2logic.cli \
    tests/fixtures/bitwig_simple.dawproject -o "$baseline")
fi

if [[ ! -d "$after" ]]; then
  cp -R "$baseline" "$after"
fi

echo "Opening $after in Logic Pro..."
echo "  1. Change ONLY track 1 volume fader (note the dB value)"
echo "  2. File → Save (overwrite this bundle)"
echo "  3. Quit Logic Pro, then press Enter here"
open -a "Logic Pro" "$after"
read -r -p "Press Enter after saving in Logic... " _

echo "Diffing OCuA strips (template Inst 1 channel 0x580000):"
cd "$root"
PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py "$baseline" "$after" --channel 0x580000
echo
echo "Record any byte offsets in daw2logic/mixer_logic.py (OCUA_VOLUME_LINEAR_OFF, etc.)"
