# Reverse-engineering helpers

## OCuA mixer (volume / pan / mute)

Logic-validated on macOS (2026-06):

| Field | Channel strip (`0xabf7` / `0x29f5` @0x70) | Notes |
|-------|-------------------------------------------|-------|
| Volume | `float32 LE @0x98` | `stored = dB + 7.5590658` (0 dB → ~7.559, −6 dB → 1.559) |
| Active flag | `@0x4e = 0x03` | Required or Logic ignores `@0x98` on load |
| Vol gate | `@0x79 = 0x3f` | Unity default is `0x5a`; required for display |

Implemented in `daw2logic/mixer_logic.py`.

### Capture a differential fixture (macOS + Logic Pro)

```bash
bash scripts/macos/capture_mixer_fixture.sh /tmp/daw2logic-re
```

Edit the **Drumloop** row fader (channel `0x640000`), not template Inst 1 / Audio 1.
The script diffs Drumloop and template Audio 1 in case the wrong row was selected.

Repeat for pan and mute.

## AU embedding

See [`docs/AU_EMBEDDING.md`](../docs/AU_EMBEDDING.md).
