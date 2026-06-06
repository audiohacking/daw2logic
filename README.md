# daw2logic

Convert [DAWproject](https://github.com/bitwig/dawproject) (`.dawproject`) files to Logic Pro (`.logicx`) projects.

The converter is a portable Python CLI (Linux and macOS, no Xcode required for the core tool). It uses [LogicProFormatWriter](https://github.com/geoffmyers/LogicProFormatWriter) to synthesize Logic `ProjectData` and writes sidecars for data that is not yet native in the binary format.

## Requirements

- Python 3.10+
- Git (for submodules)
- Logic Pro on macOS — optional, for manual playback checks and reverse-engineering fixtures

## Quick start

```bash
git clone https://github.com/audiohacking/daw2logic.git
cd daw2logic
bash scripts/setup_dev.sh   # submodules, editable installs, demo fixtures
pytest
```

Or step by step:

```bash
git submodule update --init --recursive
python3 -m venv .venv && source .venv/bin/activate
pip install -e third_party/LogicProFormatWriter
pip install -e ".[dev]"
python tests/fixtures/build_bitwig_simple.py
pytest
```

## Usage

```bash
daw2logic song.dawproject -o song.logicx
daw2logic song.dawproject -o song.logicx --report report.json
```

The CLI prints a summary (tracks, regions, tempo) and lists warnings on stderr. Use `--report` for a JSON file with warnings, skipped items, and stats.

## Dependencies (git submodules)

| Submodule | Purpose |
|-----------|---------|
| [`third_party/LogicProFormatWriter`](third_party/LogicProFormatWriter) | Writes Logic `ProjectData` / `.logicx` bundles (`logicx` Python package) |
| [`third_party/LogicFiles`](third_party/LogicFiles) | AU preset format reference; macOS validation via `scripts/macos/validate_au_sidecar.sh` |
| [`third_party/dawproject`](third_party/dawproject) | Format reference + demo WAV for test fixtures |

## What converts today

| Feature | Native in `.logicx` | Notes |
|---------|---------------------|-------|
| Tempo (constant + maps) | Yes | Via LogicProFormatWriter |
| Meter maps | Yes | |
| Markers | Yes | |
| MIDI notes + clip names | Yes | Instrument tracks |
| Audio regions | Yes | Warp-aware slice + linear resample |
| Track / region names | Yes | |
| AU plugin presets | Sidecar | Copied to `Media/daw2logic Import/plugins/` |
| Mixer volume / pan / mute | Sidecar | JSON in import manifest; native OCuA patching pending RE |
| Automation | Sidecar | Per-track JSON under `Media/daw2logic Import/automation/` |
| VST / CLAP plugins | Skipped | No Logic slot |
| Clip fades | Warning only | Not in LogicProFormatWriter yet |
| Track colors, scenes | Skipped / warning | |

After conversion, open the `.logicx` bundle in Logic Pro to verify playback. AU presets in the sidecar must be loaded manually onto channel strips until native plugin embedding is implemented.

## Sidecar layout

```
song.logicx/
  Media/daw2logic Import/
    manifest.json       # per-track plugins, mixer, automation references
    README.txt
    plugins/            # copied .aupreset files
    automation/         # automation curves as JSON
```

## Development

Tests are driven by demo fixtures built from the [Bitwig DAWproject example](third_party/dawproject/README.md):

| Fixture | Contents |
|---------|----------|
| `bitwig_simple.dawproject` | Bass MIDI + drumloop audio @ 149 BPM, mixer levels |
| `bitwig_extended.dawproject` | Tempo map + markers |
| `bitwig_au.dawproject` | AU plugin + volume automation (requires LogicFiles submodule) |

Build fixtures: `python tests/fixtures/build_bitwig_simple.py`

CI runs `pytest` on Ubuntu and macOS (Python 3.11 and 3.12) with submodules checked out recursively.

### macOS: validate bundled AU presets

```bash
daw2logic tests/fixtures/bitwig_au.dawproject -o out.logicx
bash scripts/macos/validate_au_sidecar.sh out.logicx
```

### Reverse-engineering: OCuA mixer fields

Logic stores fader/pan/mute in 205-byte `OCuA` channel strips. Offsets are not yet decoded. To contribute a differential fixture:

1. Convert a minimal project: `daw2logic tests/fixtures/bitwig_simple.dawproject -o re.logicx`
2. Open in Logic Pro, change **only** one fader, save as `re_vol.logicx`
3. Diff strips: `python tools/ocua_mixer_re.py re.logicx re_vol.logicx --channel 0x580000`

See [`scripts/re/README.md`](scripts/re/README.md) and [`daw2logic/mixer_logic.py`](daw2logic/mixer_logic.py) for wiring discovered offsets into the converter.

## Architecture

```
.dawproject (ZIP+XML)
  → parser / flatten → IR
  → logicx synthesize_av_region_bundle → .logicx
  → transport_logic (tempo / meter / markers)
  → mixer_logic (OCuA patching when offsets known)
  → plugins.export_sidecars (AU / mixer / automation JSON)
```

## License

MIT
