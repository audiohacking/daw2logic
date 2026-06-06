#!/usr/bin/env bash
# Validate AU presets bundled in a .logicx sidecar using LogicFiles (macOS only).
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
logicx="${1:?usage: validate_au_sidecar.sh Project.logicx}"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "LogicFiles validation requires macOS" >&2
  exit 2
fi

import_dir="$logicx/Media/daw2logic Import/plugins"
if [[ ! -d "$import_dir" ]]; then
  echo "no plugin sidecar at $import_dir"
  exit 0
fi

cd "$root/third_party/LogicFiles"
while IFS= read -r -d '' preset; do
  echo "validate: $preset"
  swift run logicfiles info "$preset"
done < <(find "$import_dir" -name '*.aupreset' -print0)
