# daw2logic

Convert [DAWproject](https://github.com/bitwig/dawproject) (`.dawproject`) files to Logic Pro (`.logicx`) projects.

The converter is a portable Python CLI (Linux and macOS). It uses [LogicProFormatWriter](https://github.com/geoffmyers/LogicProFormatWriter) to synthesize Logic `ProjectData` and writes sidecars for data that is not yet safe or complete in the binary format.

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
daw2logic song.dawproject -o song.logicx --force   # replace existing bundle
daw2logic song.dawproject -o song.logicx --report report.json  # optional JSON report
```

On success the CLI is quiet. Conversion notes (warnings, skipped items, stats) are written to `song.txt` beside the output bundle. Errors go to stderr. Use `--report` for structured JSON instead of or in addition to the text notes.

## Browser converter (experimental)

A WebAssembly build runs in the browser — drop a `.dawproject` file, get a `.logicx.zip` download. Nothing is uploaded to a server. Deployed via GitHub Pages on each push to `main` (see **wasm-pages** workflow). Local build: [`docs/WASM.md`](docs/WASM.md).

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
| Audio regions | Yes | Original WAVs copied; time-stretch baked only when DAWproject declares warp/stretch |
| Track / region names | Yes | Reuses mixed-base template Inst 1 / Audio 1 slots |
| Track order | Yes | Interleaved DAWproject order preserved in arrange window |
| AU plugin presets | Sidecar | Copied to `Media/daw2logic Import/plugins/` |
| Mixer volume / pan / mute | Native | Logic-validated on `bitwig_simple` / `bitwig_mixer` (±0.1 dB). `@0x79` gate + `@0x98` float |
| EQ (DAWproject Equalizer) | Sidecar | Bands → Logic Channel EQ JSON in `Media/daw2logic Import/eq/` |
| Track / clip colors | Sidecar | Parsed to manifest; native ProjectData graft disabled (corrupts Logic) |
| Automation | Sidecar | Per-track JSON under `Media/daw2logic Import/automation/` |
| VST / CLAP plugins | Skipped | No Logic slot |
| Clip fades | Warning only | Not in LogicProFormatWriter yet |
| Audio warp / trim | Warning or resample | Original file preserved unless stretch algorithm needs baking |

After conversion, open the `.logicx` bundle in Logic Pro to verify playback. AU presets, EQ, and colors in sidecars must be applied manually until native embedding is fully validated.

## Standalone binary (releases)

Pre-built executables for **Linux x86_64** and **macOS arm64** are attached to each [GitHub release](https://github.com/audiohacking/daw2logic/releases). No Python install required.

**Linux**

```bash
curl -fsSL -o daw2logic \
  https://github.com/audiohacking/daw2logic/releases/latest/download/daw2logic-linux-x86_64
chmod +x daw2logic
./daw2logic song.dawproject -o song.logicx
```

**macOS (Apple Silicon)**

```bash
curl -fsSL -o daw2logic \
  https://github.com/audiohacking/daw2logic/releases/latest/download/daw2logic-macos-arm64
chmod +x daw2logic
xattr -dr com.apple.quarantine daw2logic 2>/dev/null || true
./daw2logic song.dawproject -o song.logicx
```

Build locally: `bash scripts/build_cli.sh` (requires Python 3.11+ and PyInstaller; output under `dist/`).

## Sidecar layout

```
song.logicx/
  Media/daw2logic Import/
    manifest.json       # per-track plugins, mixer, automation, color references
    README.txt
    plugins/            # copied .aupreset files
    eq/                 # Channel EQ band data as JSON
    automation/         # automation curves as JSON
```

## Development

Tests are driven by demo fixtures built from the [Bitwig DAWproject example](third_party/dawproject/README.md):

| Fixture | Contents |
|---------|----------|
| `bitwig_simple.dawproject` | Bass MIDI + drumloop audio @ 149 BPM, mixer levels |
| `bitwig_mixer.dawproject` | Pan + mute + volume (Logic-validated) |
| `bitwig_extended.dawproject` | Tempo map + markers |
| `bitwig_interleaved.dawproject` | Same as simple but audio track before instrument |
| `bitwig_au.dawproject` | AU plugin + volume automation (requires LogicFiles submodule) |

Native AU embedding research: [`docs/AU_EMBEDDING.md`](docs/AU_EMBEDDING.md)

Build fixtures: `python tests/fixtures/build_bitwig_simple.py`

CI runs `pytest` on Ubuntu and macOS (Python 3.11 and 3.12). Publishing a GitHub release builds standalone Linux/macOS binaries and attaches them to the release (**release** workflow). WASM builds use ccache and a zlib object cache to speed up repeat runs.

### macOS: validate bundled AU presets

```bash
daw2logic tests/fixtures/bitwig_au.dawproject -o out.logicx
bash scripts/macos/validate_au_sidecar.sh out.logicx
```

### Reverse-engineering: OCuA mixer fields

Logic stores fader/pan/mute in 205-byte `OCuA` channel strips. Volume uses `@0x79` gate + `@0x98` float (see `mixer_logic.py`). To capture new calibration points:

1. Run `bash scripts/macos/capture_mixer_fixture.sh` (or convert manually, change one fader in Logic, save)
2. Diff strips: `python tools/ocua_mixer_re.py re.logicx re_vol.logicx --channel 0x580000`

Automated fader moves require Accessibility permission for Terminal/Cursor; the capture script uses a manual save step.

See [`scripts/re/README.md`](scripts/re/README.md) and [`daw2logic/mixer_logic.py`](daw2logic/mixer_logic.py) for wiring discovered offsets into the converter.

## Architecture

```
.dawproject (ZIP+XML)
  → parser / flatten → IR
  → logicx synthesize_av_region_bundle → .logicx
  → transport_logic (tempo / meter / markers)
  → track_order (reuse template Inst 1 / Audio 1; interleaved arrange reorder)
  → mixer_logic (OCuA patching when offsets known)
  → plugins.export_sidecars (AU / EQ / automation / color manifest JSON)
```

## License

MIT
