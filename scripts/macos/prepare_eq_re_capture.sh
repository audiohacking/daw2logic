#!/usr/bin/env bash
# Prepare Logic bundles for Channel EQ reverse-engineering.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

baseline="$work/eq_baseline.logicx"
after="$work/eq_channel_eq.logicx"

src="${2:-$root/tests/fixtures/bitwig_simple.dawproject}"
echo "Converting $src -> $baseline"
(cd "$root" && PYTHONPATH="third_party/LogicProFormatWriter:." python3 -m daw2logic.cli \
  "$src" -o "$baseline")

cp -R "$baseline" "$after"

cat <<EOF

=== Channel EQ capture (one track only) ===
1. Quit Logic Pro if open
2. open -a "Logic Pro" "$after"
3. Select **Drumloop** (audio row, channel 0x640000 — not template Audio 1)
4. Insert **Channel EQ** as the first audio FX on that strip
5. Set one obvious band (e.g. band 3 bell +6 dB @ 1 kHz) so the diff is visible
6. File -> Save, quit Logic
7. Diff nCuA (plugin container) for Drumloop:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/projectdata_re.py \\
     "$baseline" "$after" --tag nCuA --channel 0x640000
8. Also diff OCuA mixer strip (may grow when FX added):
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py \\
     "$baseline" "$after" --channel 0x640000

Reference CST with Channel EQ PST:
  third_party/LogicFiles/Tests/Resources/examples/Instrument with 4 MIDI FX/4 Midi FX plus 2 Audio FX.cst

Reply with diff output or "done" after capture.

EOF
