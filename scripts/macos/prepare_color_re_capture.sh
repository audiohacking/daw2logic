#!/usr/bin/env bash
# Prepare Logic bundles for track/region color reverse-engineering.
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
work="${1:-/tmp/daw2logic-re}"
mkdir -p "$work"

baseline="$work/color_baseline.logicx"
after="$work/color_changed.logicx"

src="${2:-$root/tests/fixtures/bitwig_simple.dawproject}"
echo "Converting $src -> $baseline"
(cd "$root" && PYTHONPATH="third_party/LogicProFormatWriter:." python3 -m daw2logic.cli \
  "$src" -o "$baseline")

cp -R "$baseline" "$after"

cat <<EOF

=== Track + region color capture ===
1. Quit Logic Pro if open
2. open -a "Logic Pro" "$after"
3. Select **Drumloop** track header — set track color to **red** (or any non-blue)
4. Select one **Drumloop audio region** — set region color to **green** (different from track)
5. Optionally set **Bass** track to **orange**
6. File -> Save, quit Logic
7. Diff arrange track row (karT):
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/projectdata_re.py \\
     "$baseline" "$after" --tag karT --channel 0x640000
8. Diff track qeSM cluster:
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/projectdata_re.py \\
     "$baseline" "$after" --tag qeSM --channel 0x640000
9. Diff first gRuA region on Drumloop (pick region index from arrange):
   cd "$root" && PYTHONPATH=third_party/LogicProFormatWriter python3 tools/projectdata_re.py \\
     "$baseline" "$after" --tag gRuA

DAWproject colors (for mapping): track/clip \`color="#rrggbb"\` in project.xml.

Reply with diff output or "done" after capture.

EOF
