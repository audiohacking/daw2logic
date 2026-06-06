#!/usr/bin/env bash
# Build fresh .logicx bundles and print Logic Pro mixer validation checklist.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

cd "$root"
export PYTHONPATH="third_party/LogicProFormatWriter:."

for pair in bitwig_simple bitwig_mixer; do
  out="$work/${pair}.logicx"
  rm -rf "$out"
  python3 -m daw2logic.cli "tests/fixtures/${pair}.dawproject" -o "$out"
done

python3 <<'PY'
import math, struct
from pathlib import Path
from logicx.projectdata import ProjectData, _ocua_for_channel
from daw2logic.logicx_channels import instrument_channels, audio_channels

work = Path("/tmp/daw2logic-re")

def fmt(path, tname, ch, exp_vol, exp_pan, exp_mute):
    pd = ProjectData.parse((path / "Alternatives/000/ProjectData").read_bytes())
    raw = _ocua_for_channel(pd, ch).raw
    db = struct.unpack_from("<f", raw, 0x98)[0] - 7.5590658
    pan = raw[0x7d] - 64
    mute = raw[0x7e]
    exp_db = 20 * math.log10(exp_vol)
    exp_pan_logic = round(exp_pan * 127) - 64
    print(f"  {tname}:")
    print(f"    volume: {db:+.1f} dB  (expect {exp_db:+.1f})")
    print(f"    pan:    {pan:+d}      (expect {exp_pan_logic:+d})")
    print(f"    mute:   {'yes' if mute else 'no':3s}     (expect {'yes' if exp_mute else 'no'})")

for bundle, specs in [
    ("bitwig_simple.logicx", [
        ("Bass", "inst", 2, 0.659140, 0.5, False),
        ("Drumloop", "aud", 2, 0.177125, 0.5, False),
    ]),
    ("bitwig_mixer.logicx", [
        ("Bass", "inst", 2, 0.659140, 0.25, True),
        ("Drumloop", "aud", 2, 0.177125, 0.75, False),
    ]),
]:
    path = work / bundle
    print(f"\n{bundle}  ->  {path}")
    pd = ProjectData.parse((path / "Alternatives/000/ProjectData").read_bytes())
    ic, ac = instrument_channels(pd), audio_channels(pd)
    for tname, kind, ord_, vol, pan, mute in specs:
        ch = ic[ord_] if kind == "inst" else ac[ord_]
        fmt(path, tname, ch, vol, pan, mute)
PY

cat <<EOF

=== Logic Pro manual check ===
Quit Logic, then open ONE file at a time:

  1. $work/bitwig_simple.logicx
     Bass:     ~-3.6 dB, center pan, unmuted
     Drumloop: ~-15.0 dB, center pan, unmuted

  2. $work/bitwig_mixer.logicx
     Bass:     ~-3.6 dB, L32, muted
     Drumloop: ~-15.0 dB, R31, unmuted

Use the **Bass** and **Drumloop** rows (not template Inst 1 / Audio 1).
Reply with:  simple OK / mixer OK  or list any mismatches.

EOF
