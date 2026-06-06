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
