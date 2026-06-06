#!/usr/bin/env bash
# Five empty audio tracks for Logic volume RE (-6 / -3 / 0 / +3 / +6 dB sweep).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
template="$root/third_party/LogicProFormatWriter/fixtures/lots of audio tracks/5 audio tracks.logicx"
out="$work/volume_sweep.logicx"

mkdir -p "$work"
rm -rf "$out"
cp -R "$template" "$out"

cd "$root"
export PYTHONPATH="third_party/LogicProFormatWriter:."

python3 <<'PY'
from pathlib import Path
from logicx.projectdata import ProjectData, set_track_name

out = Path("/tmp/daw2logic-re/volume_sweep.logicx")
pd_path = out / "Alternatives/000/ProjectData"
pd = ProjectData.parse(pd_path.read_bytes())
labels = ["Vol -6", "Vol -3", "Vol 0", "Vol +3", "Vol +6"]
for i, label in enumerate(labels, start=1):
    set_track_name(pd, i, label)
pd_path.write_bytes(pd.serialize())
print(f"wrote {out}")
for i, label in enumerate(labels, start=1):
    print(f"  track {i}: {label}")
PY

cp -R "$out" "$work/volume_sweep_baseline.logicx"

cat <<EOF

=== Volume sweep capture ===
File to open in Logic: $work/volume_sweep_baseline.logicx
(Keep a pristine copy at volume_sweep_baseline.logicx — open that file directly.)

1. Quit Logic Pro
2. open -a "Logic Pro" "$out"
3. Set each track fader (top to bottom in the mixer):
     Vol -6  ->  -6.0 dB
     Vol -3  ->  -3.0 dB
     Vol 0   ->   0.0 dB
     Vol +3  ->  +3.0 dB
     Vol +6  ->  +6.0 dB
4. File -> Save (same bundle), quit Logic
5. Reply "volume sweep done"

Save as: $out  (overwrite is fine)

EOF
