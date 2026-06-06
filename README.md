# daw2logic

Convert [DAWproject](https://github.com/bitwig/dawproject) files to Logic Pro `.logicx` projects.

## Dependencies (git submodules)

```bash
git submodule update --init --recursive
```

| Submodule | Purpose |
|-----------|---------|
| [`third_party/LogicProFormatWriter`](third_party/LogicProFormatWriter) | Writes Logic `ProjectData` / `.logicx` bundles (`logicx` Python package) |
| [`third_party/LogicFiles`](third_party/LogicFiles) | AU preset format reference; macOS validation via `scripts/macos/validate_au_sidecar.sh` |
| [`third_party/dawproject`](third_party/dawproject) | Format reference + demo WAV for test fixtures |

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e third_party/LogicProFormatWriter
pip install -e ".[dev]"
python tests/fixtures/build_bitwig_simple.py   # build demo .dawproject fixture
pytest
```

## Usage

```bash
daw2logic song.dawproject -o song.logicx
daw2logic song.dawproject -o song.logicx --report warnings.json
```

## Development

- Tests drive development against `tests/fixtures/bitwig_simple.dawproject`, built from the [Bitwig example](third_party/dawproject/README.md) and `third_party/dawproject/test-data/white-glasses.wav`.
- Open `out.logicx` in Logic Pro on macOS to validate playback (not automated in CI).

## Status

Imports tempo maps, meter maps, markers, MIDI notes, and audio regions (with
warp-aware slice/resample). AU plugin presets, mixer levels, and automation
curves are exported under `Media/daw2logic Import/` in the `.logicx` bundle.
VST/CLAP plugins and native Logic channel-strip/plugin embedding require
ProjectData writers not yet available (see `daw2logic/mixer_logic.py` and
`scripts/re/README.md` for OCuA mixer RE workflow).

### macOS: validate bundled AU presets

```bash
bash scripts/macos/validate_au_sidecar.sh out.logicx
```
