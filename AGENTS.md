# daw2logic — agent session notes

Persistent context for AI agents and contributors. Read this before large changes. Deeper WASM detail: [`docs/WASM.md`](docs/WASM.md).

## What this project does

Converts **DAWproject** (`.dawproject` zip + XML) → **Logic Pro** (`.logicx` bundle).

- **CLI / release binaries**: `daw2logic.cli` → `daw2logic.convert` → [LogicProFormatWriter](third_party/LogicProFormatWriter) `synthesize_av_region_bundle`
- **Browser WASM**: same converter via `daw2logic/wasm_api.py`, packaged as `web/wasm/daw2logic.wasm`, UI at `web/`
- **Live demo**: https://audiohacking.github.io/daw2logic/

Submodules (required):

| Path | Role |
|------|------|
| `third_party/LogicProFormatWriter` | `logicx` package + donor seeds in `logicx/data/` |
| `third_party/dawproject` | Format reference + demo WAV for fixtures |
| `third_party/LogicFiles` | AU preset parsing (macOS validation scripts) |

We **cannot push** to `jonkubis/LogicProFormatWriter`. WASI-specific logicx changes live in `scripts/patches/logicx-wasi-seeds.patch` and are applied at WASM build time by `scripts/build_wasm.sh`.

## Architecture (happy path)

```
.dawproject (zip)
  → daw2logic.parser.load / flatten → IR
  → daw2logic.convert.convert
       → MIDI/audio regions via logicx.projectdata
       → transport_logic, track_order, mixer_logic, plugins.export_sidecars
  → .logicx/ directory bundle
```

WASM path wraps the same `convert()` but writes a **zip download** via `wasm_api._zip_logicx_bundle()`.

## Audio policy (important)

**Default: do not re-encode WAVs.** Copy embedded audio unchanged into `Media/Audio Files/`.

- `daw2logic/audio.py`: `resolve_audio_clip()` passes the original file unless `needs_audio_processing()` is true.
- Processing (slice + linear resample) only when DAWproject declares a **stretch algorithm** (`algorithm != "none"`) **and** timeline length ≠ source length.
- Warps, trims, fades → warnings; not baked into files unless stretch processing runs.
- Resampler supports 16- and 24-bit PCM (`prepare_audio_clip()`).

Do not revert to always slicing/resampling on every clip.

## WASM build stack

Build: `bash scripts/build_wasm.sh` (Python **3.11** only, uses `.venv-wasm`).

| Piece | Purpose |
|-------|---------|
| `wasm/main.py` | WASI stdin/stdout entry; sets `LOGICX_DATA_DIR=/seeds` |
| `scripts/patch_nuitka_wasi.py` | Patches Nuitka loader to call linked `PyInit_zlib` (zipfile needs zlib) |
| `scripts/build_wasi_zlib.sh` | Compiles zlib + `zlibmodule.c` for wasm32-wasi; uses **platform SDK** `sdk-{Linux\|Darwin\|Windows}`, not hardcoded Darwin |
| `scripts/patches/logicx-wasi-seeds.patch` | WASI seed loading via mounted `/seeds` (pkgutil/Nuitka package-data breaks on WASI) |
| `web/wasm/logicx/data/` | Copied seeds at build time (gitignored); **not** in git |

**Runtime seeds**

- CLI smoke: `wasmer run --volume "$WEB_DATA:/seeds" daw2logic.wasm < fixture`
- Browser: `web/app.js` fetches `web/wasm/logicx/data/*` and mounts at `/seeds` via `@wasmer/sdk`

**WASM zip export** (`wasm_api.py`)

- WASI temp files have meaningless mtimes (often epoch 0). Never use `ZipFile.write()` with file stat times.
- Use explicit `ZipInfo.date_time = time.gmtime()` at conversion time (current clock, not 1980 clamp).

**Wire format** (stdout): `u32 notes_len`, `u32 zip_len`, notes utf-8, logicx zip bytes.

## Release binaries (CLI)

- Build: `bash scripts/build_cli.sh` → PyInstaller one-file in `dist/`
- Assets: `daw2logic-linux-x86_64`, `daw2logic-macos-arm64`
- Entry: `scripts/cli_entry.py`
- Workflow: `.github/workflows/release.yml` on `release: published` only
- README curl: `/releases/latest/download/<asset-name>`

## CI workflows

| Workflow | Trigger | Notes |
|----------|---------|-------|
| `test.yml` | push/PR | pytest on ubuntu + macos, Python 3.11/3.12 |
| `wasm-pages.yml` | push main | build wasm, smoke test, deploy `web/` to Pages |
| `release.yml` | release published | PyInstaller matrix → attach to release |

**ccache**: reusable action `.github/actions/setup-ccache` (skip save on PRs). Used in wasm-pages (+ `tmp/wasi-zlib` object cache) and release builds. `build_wasi_zlib.sh` wraps clang with ccache when available.

## Local dev commands

```bash
bash scripts/setup_dev.sh          # submodules + editable install + fixtures
pytest                             # full suite
python tests/fixtures/build_bitwig_simple.py
bash scripts/build_wasm.sh         # ~90s; smoke tests with wasmer
bash scripts/build_cli.sh          # standalone executable in dist/
python -m http.server 8080 --directory web   # preview WASM UI
```

## Do not commit

- `web/wasm/*.wasm`, `web/wasm/logicx/` (build outputs)
- `.venv-wasm/`, `.venv-release/`, `tmp/`, `dist/`, `build/pyinstaller/`, `*.spec`
- `nuitka-crash-report.xml`
- `tests/fixtures/DAWTEST.dawproject` (local user fixture; keep untracked unless explicitly requested)
- Dirty submodule state from applied WASI patches

## Web UI

- `web/index.html`, `web/app.js`, `web/styles.css`
- Logo: `web/logo.png` (also favicon); README may use GitHub CDN URL for the same image
- COOP/COEP: `web/coi-serviceworker.js` (fetched in CI)

## Common failure modes (seen in production)

| Symptom | Likely cause |
|---------|----------------|
| `unsupported sample width: 24-bit` | Stretch path + old resampler (fixed); or unexpected audio processing |
| `ZIP does not support timestamps before 1980` | Using file mtimes from WASI in zip (fixed: use current time) |
| `[Errno 54] Not a directory: ./logicx/data/...` | Seeds not mounted at `/seeds` (CLI or browser) |
| `wasi clang not found at ... sdk-Darwin` | Linux CI using Darwin SDK path (fixed: dynamic `sdk-{platform}`) |
| `dlopen` / empty zlib on WASI | Missing `build_wasi_zlib.sh` + Nuitka patch |
| Submodule push denied | Use patch file, don't bump LogicProFormatWriter pointer for WASI-only fixes |

## Conventions for agents

- **Minimize scope**; match existing patterns in `daw2logic/` and LogicProFormatWriter usage.
- **Only commit when asked**; never commit secrets or build artifacts.
- **Tests**: `tests/fixtures/*.dawproject` are tracked; user-local fixtures like `DAWTEST.dawproject` usually are not.
- **Docs**: user-facing WASM details → `docs/WASM.md`; this file → agent/session continuity.
- After WASM Python changes, **wasm-pages must rebuild** `daw2logic.wasm` for the browser demo to update.

## Key files (quick index)

```
daw2logic/convert.py       conversion orchestration
daw2logic/audio.py         pass-through vs stretch audio
daw2logic/wasm_api.py      in-memory convert + zip + wire format
daw2logic/parser.py        .dawproject load
wasm/main.py               WASI entry + nuitka-project lines
scripts/build_wasm.sh      full WASM pipeline
scripts/build_cli.sh       PyInstaller release binary
web/app.js                 browser Wasmer runner + seed mount
.github/workflows/         CI / Pages / release
```
