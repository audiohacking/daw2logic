# Reverse-engineering helpers

## OCuA mixer (volume / pan / mute)

Logic stores fader state in 205-byte `OCuA` channel strips. Offsets are not yet
decoded in LogicProFormatWriter; daw2logic exports mixer JSON sidecars until they are.

### Capture a differential fixture (macOS + Logic Pro)

```bash
bash scripts/macos/capture_mixer_fixture.sh /tmp/daw2logic-re
```

This builds `re.logicx`, opens a copy in Logic Pro, waits for you to change **one**
fader and save, then runs `tools/ocua_mixer_re.py` against the baseline.

**Blocker:** unattended GUI automation needs Accessibility permission for your
terminal app. Without it, use the manual save step in the script.

Repeat for pan and mute. Record offsets in `daw2logic/mixer_logic.py`
(`OCUA_VOLUME_LINEAR_OFF`, etc.) and add a regression test.

## AU embedding

See [`docs/AU_EMBEDDING.md`](../docs/AU_EMBEDDING.md).
