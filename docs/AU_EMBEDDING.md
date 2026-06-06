# AU preset embedding in Logic ProjectData

## Current state

daw2logic copies `.aupreset` files into `Media/daw2logic Import/plugins/` and records
metadata in `manifest.json`. Logic Pro does **not** load these automatically — the user
must drag presets onto channel strips.

Validation on macOS: `scripts/macos/validate_au_sidecar.sh` uses the LogicFiles submodule
to parse bundled presets (`swift run logicfiles info`).

## Target: native AU on instrument tracks

Logic stores plugin state in **`UCuA`** records (NSKeyedArchiver plists, idx `0x240000`),
linked to instrument **`ivnE`** environment channels. This is separate from the 205-byte
**`OCuA`** mixer strip (fader/pan/mute).

LogicProFormatWriter already materializes instrument infrastructure via differential
cloning (`instrument_infrastructure`, `_heavy_activate_instrument`, `_set_instrument_ucua`).
See `third_party/LogicProFormatWriter/PROJECTDATA_FORMAT.md` §10.9.1.

## What we parse today

From DAWproject (`daw2logic/parser.py`):

- `AuPlugin` elements with optional `state` path to embedded `.aupreset`
- Preset copied and summarized via `daw2logic/aupreset.py` (component subtype, manufacturer, payload size)

## Embedding path (research summary)

| Step | Work | Owner |
|------|------|-------|
| 1 | Map DAWproject `deviceID` / component IDs to Logic AU four-char codes | daw2logic |
| 2 | Deserialize `.aupreset` payload (LogicFiles `PATCH_FORMAT.md`) | LogicFiles ref |
| 3 | Clone UCuA plist envelope from `instrument_infrastructure` donor | LPW |
| 4 | Graft preset bytes into UCuA for the target instrument channel | LPW + daw2logic |
| 5 | Logic validation: open `.logicx`, confirm plugin loads | macOS manual |

## Blockers

1. **UCuA grafting is not exposed** in LPW's public API — only empty instrument channels are synthesized today.
2. **Per-plugin plist shape** varies (Apple vs third-party AUs); LogicFiles documents `.aupreset` containers, not in-project UCuA layout.
3. **Wrong-plugin safety** — embedding requires matching component type/manufacturer; mismatches crash or silent-fail in Logic.

## Recommended sequence

1. Finish **OCuA mixer RE** (volume/pan/mute) — same channel strip family, smaller scope.
2. Contribute **`patch_instrument_ucua_preset(pd, inst_ordinal, aupreset_path)`** to LogicProFormatWriter using `mixed_template + 1 inst` differential donors.
3. Wire **`daw2logic/plugins.py`** to call native embed when LPW API exists; keep sidecar as fallback.

## Prototype hook (daw2logic)

When LPW supports UCuA grafting:

```python
# daw2logic/plugins_logic.py (future)
def apply_au_presets(logicx_dir, project, report):
    for track in project.tracks:
        for plugin in track.plugins:
            if plugin.kind != "au" or not plugin.resolved_path:
                continue
            # map track → logic_inst_ordinal, call LPW graft
            ...
```

Track → channel mapping should reuse `track_order.export_channel_order` and
`logic_inst_ordinal()` for instrument tracks.

## References

- `third_party/LogicFiles/Sources/Models/PATCH_FORMAT.md`
- `third_party/LogicProFormatWriter/DONORS.md` — `mixed_1inst`, `mixed_2inst` fixtures
- `third_party/LogicProFormatWriter/logicx/projectdata.py` — `_set_instrument_ucua`, `_heavy_activate_instrument`
