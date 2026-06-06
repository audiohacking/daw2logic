# Browser / WASM prototype

Experimental branch that compiles daw2logic to WebAssembly with [py2wasm](https://wasmer.io/posts/py2wasm-a-python-to-wasm-compiler) (Nuitka WASI fork) and serves a static web UI on GitHub Pages.

## Architecture

```
Browser (web/)
  └─ @wasmer/sdk runs daw2logic.wasm (WASI)
       └─ stdin: .dawproject zip bytes
       └─ stdout: framed notes + .logicx.zip bytes

Python sources
  wasm/main.py          WASI entry (stdin/stdout)
  daw2logic/wasm_api.py in-memory convert + wire format
```

The web app never uploads files to a server — conversion runs entirely in the browser once the WASM module is loaded.

## Local development

### 1. Test the in-memory API (no WASM)

```bash
python tests/fixtures/build_bitwig_simple.py
pytest tests/test_wasm_api.py -q
```

### 2. Build the WASM module

Requires **Python 3.11** and a C compiler (`clang` / `gcc`).

```bash
bash scripts/build_wasm.sh
```

This installs the Wasmer py2wasm fork into `.venv-wasm`, compiles `wasm/main.py` → `web/wasm/daw2logic.wasm`, and smoke-tests with `wasmer run` when available.

### 3. Preview the web UI

Serve the `web/` directory over HTTP (required for ES modules + WASM fetch):

```bash
python -m http.server 8080 --directory web
open http://localhost:8080
```

For `@wasmer/sdk` threading, the page uses [coi-serviceworker](https://github.com/gzuidhof/coi-serviceworker) to enable cross-origin isolation headers locally and on GitHub Pages.

## GitHub Pages

Push to the `wasm` branch — the **wasm-pages** workflow:

1. Checks out submodules (LogicProFormatWriter seeds are required at compile time)
2. Builds `web/wasm/daw2logic.wasm` on Ubuntu
3. Deploys the `web/` folder to GitHub Pages

Enable Pages in repo settings: **Source → GitHub Actions**.

## Known constraints / blockers

| Topic | Status |
|-------|--------|
| py2wasm on PyPI | Standard PyPI `py2wasm` is upstream Nuitka **without** WASI — use the [lum1n0us fork](https://github.com/lum1n0us/Nuitka/tree/dev/wasi_sync_upstream) via `scripts/build_wasm.sh` |
| Python version | WASM build requires **3.11** (not 3.12+) |
| Binary size | Full converter + libpython WASM is large (expect tens of MB) |
| Browser headers | Needs COOP/COEP for Wasmer SDK; handled via service worker on Pages |
| Folder drop | UI currently accepts `.dawproject` files only; folder → zip client-side is TODO |
| AU sidecars | Same as CLI — presets export to sidecar paths inside the bundle zip |

If the WASI fork stops working, fallbacks to evaluate: Pyodide (interpreter, easier but slower) or a Rust/WASM rewrite of the hot path.

## Wire format

```
u32 notes_len LE
u32 zip_len LE
notes_utf8[notes_len]
logicx_zip[zip_len]
```

Implemented in `daw2logic/wasm_api.py` (`pack_conversion_result` / `unpack_conversion_result`).
