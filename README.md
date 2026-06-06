# daw2logic

Convert [DAWproject](https://github.com/bitwig/dawproject) files to Logic Pro `.logicx` projects.

## Dependencies (git submodules)

```bash
git submodule update --init --recursive
```

| Submodule | Purpose |
|-----------|---------|
| [`third_party/LogicProFormatWriter`](third_party/LogicProFormatWriter) | Writes Logic `ProjectData` / `.logicx` bundles (`logicx` Python package) |
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

Imports tempo maps, meter maps, markers, MIDI notes (with clip names), and audio
regions (with warp-aware slice/resample, clip names, and region length). Reports
unsupported features (plugins, mixer automation, fades, scenes, track colors) in
`--report` warnings/skipped lists.
