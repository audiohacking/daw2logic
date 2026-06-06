# Reverse-engineering helpers

## OCuA mixer (volume / pan / mute)

Logic stores fader state in 205-byte `OCuA` channel strips. Offsets are not yet
decoded in LogicProFormatWriter; daw2logic exports mixer JSON sidecars until they are.

### Capture a differential fixture

1. Convert a minimal project: `daw2logic tests/fixtures/bitwig_simple.dawproject -o re.logicx`
2. Open `re.logicx` in Logic Pro on macOS.
3. Change **only** the volume fader on track 1 (note the dB value).
4. Save as `re_vol.logicx` (duplicate bundle or Save As).
5. Diff strips:

```bash
python tools/ocua_mixer_re.py re.logicx re_vol.logicx --channel 0x580000
```

Repeat for pan and mute. Record offsets in `daw2logic/mixer_logic.py`
(`OCUA_VOLUME_LINEAR_OFF`, etc.) and add a regression test.
