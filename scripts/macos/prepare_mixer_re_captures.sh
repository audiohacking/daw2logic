#!/usr/bin/env bash
# Build Logic bundles for pan/mute reverse-engineering captures.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

baseline="$work/mixer_baseline.logicx"
pan_after="$work/drumloop_pan_left.logicx"
mute_after="$work/bass_muted.logicx"

echo "Converting bitwig_simple -> $baseline"
(cd "$root" && PYTHONPATH="third_party/LogicProFormatWriter:." python3 -m daw2logic.cli \
  tests/fixtures/bitwig_simple.dawproject -o "$baseline")

cp -R "$baseline" "$pan_after"
cp -R "$baseline" "$mute_after"

cat <<EOF

=== Manual capture A: pan (Drumloop only) ===
1. Quit Logic Pro if open
2. open -a "Logic Pro" "$pan_after"
3. Select track **Drumloop** (not Inst 1 / Audio 1)
4. Move pan knob to **hard left** (L100 or minimum)
5. File -> Save, quit Logic
6. Run:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py \\
     "$baseline" "$pan_after" --channel 0x640000

=== Manual capture B: mute (Bass only) ===
1. Quit Logic Pro if open
2. open -a "Logic Pro" "$mute_after"
3. Select track **Bass** (instrument row, not Inst 1 template)
4. Click **Mute** on that strip only
5. File -> Save, quit Logic
6. Run:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py \\
     "$baseline" "$mute_after" --channel 0x600000

Reply with the diff output (or just "done") after each capture.

EOF
