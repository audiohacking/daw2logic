# Reverse-engineering helpers

## OCuA mixer (volume / pan / mute)

Logic-validated on macOS (2026-06), including `volume_sweep_baseline.logicx`:

| Field | Channel strip (`0xabf7` / `0x29f5` @0x70) | Notes |
|-------|-------------------------------------------|-------|
| Volume | `float32 LE @0x98` | Often `stored = dB + 7.5590658`; see captures |
| **Vol gate** | **`@0x79`** | **Must equal float byte `@0x9b`** |
| Active flag | `@0x4e = 0x03` | Required or Logic ignores volume on load |
| Unity | `@0x79=0x5a`, `@0x98=0000005a` | 0 dB |
| Sweep captures | see `OCUA_VOLUME_CAPTURES` in `mixer_logic.py` | −6/−3/0/+3/+6 dB |
| Pan | `@0x7d` uint8 | `round(normalized * 127)` |
| Mute | `@0x7e` | `0x01` muted, `0x00` unmuted |

Implemented in `daw2logic/mixer_logic.py`.

### Volume sweep fixture

```bash
bash scripts/macos/prepare_volume_sweep_capture.sh /tmp/daw2logic-re
```

Authoritative capture: **`volume_sweep_baseline.logicx`** (Logic shows −6/−3/0/+3/+6 on the five tracks).

### Pan / mute captures

```bash
bash scripts/macos/prepare_mixer_re_captures.sh /tmp/daw2logic-re
```

## AU embedding

See [`docs/AU_EMBEDDING.md`](../docs/AU_EMBEDDING.md).

## Channel EQ (Logic built-in)

Logic stores **Channel EQ** as a **GAMETSPP PST** inside **UCuA** records on the plugin slot
(`channel - 0x400000`, e.g. Drumloop `0x640000` → slot `0x240000`). Requires the **2128-byte
`nCuA`** container (present on Drumloop in `bitwig_simple`; same on GREASE1 `2 Drums`).

**RE capture (2026-06):** `eq_baseline.logicx` = `bitwig_simple` after adding Channel EQ on
Drumloop (+6 dB on ~100 Hz band). Diff vs fresh convert adds:

- UCuA **464 + 339 + 384** bytes (464 holds Channel EQ PST)
- OCuA **241-byte** strip (replaces active 205-byte `@0x4e==0x03` strip)
- **5 byte** patches on 2128-byte `nCuA` @ `0x67, 0x82, 0x88, 0x92, 0x98`

Fixtures: `daw2logic/fixtures/channel_eq/`. Implementation: `daw2logic/eq_logic.py`.

PST band-1 floats (payload index): freq **10**, gain **11**, Q **12**, on **13** (validated vs
Logic CST + capture). Bands 2–6 use RE'd index tables; high-pass / 168-byte-only `nCuA` tracks
stay sidecar-only.

```bash
bash scripts/macos/prepare_eq_re_capture.sh /tmp/daw2logic-re
python3 tools/projectdata_re.py eq_baseline.logicx eq_channel_eq.logicx --tag UCuA --channel 0x240000
```

Reference CST: `third_party/LogicFiles/Tests/Resources/examples/Instrument with 4 MIDI FX/4 Midi FX plus 2 Audio FX.cst`

## Track / region colors

DAWproject exports `#rrggbb` on `<Track>` and `<Clip>`. Logic uses a **palette index** (`Channel_seqColorIndex` in patch plists; ProjectData offset TBD).

daw2logic parses track + clip colors into the IR/manifest with a nearest Logic palette guess (`daw2logic/colors.py`).

**Next:** color RE capture — change track + region colors in Logic, diff `karT` / `qeSM` / `gRuA`:

```bash
bash scripts/macos/prepare_color_re_capture.sh /tmp/daw2logic-re
python3 tools/projectdata_re.py color_baseline.logicx color_changed.logicx --tag karT --channel 0x640000
```
