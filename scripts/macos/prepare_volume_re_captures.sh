#!/usr/bin/env bash
# Prepare Logic bundles for volume RE captures outside the validated ~-6 dB band.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

baseline="$work/mixer_baseline.logicx"
drum15="$work/drumloop_minus15db.logicx"
bass3="$work/bass_minus3db.logicx"

if [[ ! -d "$baseline" ]]; then
  echo "Converting bitwig_simple -> $baseline"
  (cd "$root" && PYTHONPATH="third_party/LogicProFormatWriter:." python3 -m daw2logic.cli \
    tests/fixtures/bitwig_simple.dawproject -o "$baseline")
fi

cp -R "$baseline" "$drum15"
cp -R "$baseline" "$bass3"

cat <<EOF

=== Volume RE captures needed ===
Logic fader display is driven by OCuA @0x98. Only ~-6 dB is validated so far.
karT @0x48 does NOT override OCuA (confirmed: both tracks showed -6.0 with token).

--- Capture A: Drumloop -15 dB (audio strip) ---
1. Quit Logic Pro
2. open -a "Logic Pro" "$drum15"
3. Select **Drumloop** (not Inst 1 / Audio 1)
4. Set volume fader to **-15.0 dB** (type in the value if needed)
5. File -> Save, quit Logic
6. Run:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py \\
     "$baseline" "$drum15" --channel 0x640000

--- Capture B: Bass -3.6 dB (instrument strip) ---
1. Quit Logic Pro
2. open -a "Logic Pro" "$bass3"
3. Select **Bass** (synthesized instrument row, not Inst 1)
4. Set volume fader to **-3.6 dB** (or -3.5 dB if Logic rounds)
5. File -> Save, quit Logic
6. Run:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/ocua_mixer_re.py \\
     "$baseline" "$bass3" --channel 0x600000

Reply "volume captures done" with both diff outputs (or paste them).

EOF
