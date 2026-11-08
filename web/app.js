/**
 * Browser runner for the py2wasm-compiled daw2logic module.
 *
 * Wire format (stdout): u32 notes_len LE, u32 zip_len LE, notes utf-8, zip bytes.
 */

import { init, Wasmer } from "https://cdn.jsdelivr.net/npm/@wasmer/sdk@0.9.0/dist/index.mjs";

const WASM_URL = new URL("./wasm/daw2logic.wasm", import.meta.url);
const SEEDS_BASE = new URL("./wasm/logicx/data/", import.meta.url);
const SEED_FILES = ["audio_base.seed", "mixed_base.seed", "infra.json.gz"];
const SDK_WASM_URL =
  "https://cdn.jsdelivr.net/npm/@wasmer/sdk@0.9.0/dist/wasmer_js_bg.wasm";

const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const notesEl = document.getElementById("notes");
const downloadLogicx = document.getElementById("download-logicx");
const downloadNotes = document.getElementById("download-notes");

let runtimeReady;
/** @type {Uint8Array | null} */
let wasmBytesCache = null;
/** @type {Promise<Record<string, Uint8Array>> | null} */
let seedsReady = null;

function setStatus(message, kind = "") {
  statusEl.classList.remove("hidden", "error", "ok");
  statusEl.textContent = message;
  if (kind) statusEl.classList.add(kind);
}

function hideResults() {
  resultsEl.classList.add("hidden");
}

function showResults(notes, logicxZip, baseName) {
  notesEl.textContent = notes;
  const notesBlob = new Blob([notes], { type: "text/plain;charset=utf-8" });
  const zipBlob = new Blob([logicxZip], { type: "application/zip" });
  downloadNotes.href = URL.createObjectURL(notesBlob);
  downloadNotes.download = `${baseName}.txt`;
  downloadLogicx.href = URL.createObjectURL(zipBlob);
  downloadLogicx.download = `${baseName}.logicx.zip`;
  resultsEl.classList.remove("hidden");
}

async function loadSeedMount() {
  /** @type {Record<string, Uint8Array>} */
  const seeds = {};
  for (const name of SEED_FILES) {
    const response = await fetch(new URL(name, SEEDS_BASE));
    if (!response.ok) {
      throw new Error(
        `Seed file missing (${response.status}): ${name}. Build with scripts/build_wasm.sh or wait for the GitHub Pages workflow.`
      );
    }
    seeds[name] = new Uint8Array(await response.arrayBuffer());
  }
  return seeds;
}

async function waitForCrossOriginIsolation(timeoutMs = 8000) {
  if (window.crossOriginIsolated) {
    sessionStorage.removeItem("daw2logic_coi_reloads");
    return;
  }

  if ("serviceWorker" in navigator) {
    const regs = await navigator.serviceWorker.getRegistrations();
    if (regs.length && !navigator.serviceWorker.controller) {
      const reloads = Number(sessionStorage.getItem("daw2logic_coi_reloads") || "0");
      if (reloads < 3) {
        sessionStorage.setItem("daw2logic_coi_reloads", String(reloads + 1));
        setStatus("Enabling cross-origin isolation (required for WASM)…");
        window.location.reload();
        await new Promise(() => {});
      }
    }
  }

  const deadline = Date.now() + timeoutMs;
  while (!window.crossOriginIsolated && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  if (!window.crossOriginIsolated) {
    throw new Error(
      "This page is not cross-origin isolated, so Wasmer cannot run. " +
        "Hard-refresh once (or clear site data for this origin) and try again. " +
        "Local preview: bash scripts/serve_web.sh"
    );
  }
  sessionStorage.removeItem("daw2logic_coi_reloads");
}

async function ensureRuntime() {
  if (!runtimeReady) {
    runtimeReady = (async () => {
      setStatus("Preparing secure WASM environment…");
      await waitForCrossOriginIsolation();
      setStatus("Loading WebAssembly runtime…");
      await init({ module: SDK_WASM_URL });
      const response = await fetch(WASM_URL);
      if (!response.ok) {
        throw new Error(
          `WASM module not found (${response.status}). Build with scripts/build_wasm.sh or wait for the GitHub Pages workflow.`
        );
      }
      wasmBytesCache = new Uint8Array(await response.arrayBuffer());
      seedsReady = loadSeedMount();
      await seedsReady;
      return wasmBytesCache;
    })();
  }
  return runtimeReady;
}

function unpackResult(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.byteLength < 8) throw new Error("truncated converter output");
  const notesLen = view.getUint32(0, true);
  const zipLen = view.getUint32(4, true);
  const expected = 8 + notesLen + zipLen;
  if (expected !== bytes.byteLength) {
    throw new Error(
      `converter output length mismatch (expected ${expected}, got ${bytes.byteLength})`
    );
  }
  const notes = new TextDecoder().decode(bytes.subarray(8, 8 + notesLen));
  const logicxZip = bytes.subarray(8 + notesLen);
  return { notes, logicxZip };
}

async function convertBytes(inputBytes, sourceName) {
  await ensureRuntime();
  setStatus("Converting…");

  const wasmBytes = wasmBytesCache;
  const seeds = await seedsReady;
  if (!wasmBytes || !seeds) {
    throw new Error("WASM runtime not initialized");
  }

  // Official Wasmer pattern: run → wait() only. Do NOT touch instance.stdout /
  // stderr streams — concurrent stream reads nest LocalPool and panic.
  const pkg = await Wasmer.fromFile(wasmBytes);
  if (!pkg.entrypoint) {
    throw new Error("compiled module has no WASI entrypoint");
  }

  const instance = await pkg.entrypoint.run({
    stdin: inputBytes,
    mount: { "/seeds": seeds },
  });
  const output = await instance.wait();

  if (!output.ok) {
    const errText = String(output.stderr || "").trim();
    throw new Error(errText || `converter exited with code ${output.code}`);
  }

  const stdout = output.stdoutBytes;
  if (!(stdout instanceof Uint8Array) || stdout.byteLength === 0) {
    throw new Error("converter produced empty output");
  }

  const { notes, logicxZip } = unpackResult(stdout);
  const baseName = sourceName.replace(/\.dawproject$/i, "") || "converted";
  setStatus("Conversion complete.", "ok");
  showResults(notes, logicxZip, baseName);
}

async function fileToDawprojectBytes(file) {
  if (file.name.toLowerCase().endsWith(".dawproject")) {
    return { bytes: new Uint8Array(await file.arrayBuffer()), name: file.name };
  }
  throw new Error("Please drop a .dawproject file (folder import coming soon).");
}

async function handleFiles(fileList) {
  hideResults();
  const file = fileList?.[0];
  if (!file) return;
  try {
    const { bytes, name } = await fileToDawprojectBytes(file);
    await convertBytes(bytes, name);
  } catch (err) {
    console.error(err);
    setStatus(err.message || String(err), "error");
  }
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    fileInput.click();
  }
});
fileInput.addEventListener("change", () => handleFiles(fileInput.files));

dropzone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragover");
  handleFiles(event.dataTransfer.files);
});

ensureRuntime()
  .then(() => setStatus("Ready — drop a .dawproject file to convert."))
  .catch((err) => setStatus(err.message || String(err), "error"));

// Localhost-only hook for automated smoke tests.
if (location.hostname === "127.0.0.1" || location.hostname === "localhost") {
  window.__daw2logicSmoke = async (url = "/_test.dawproject") => {
    const bytes = new Uint8Array(await (await fetch(url)).arrayBuffer());
    await convertBytes(bytes, "smoke.dawproject");
    return {
      status: statusEl.textContent,
      notes: notesEl.textContent.slice(0, 200),
      hasDownload: Boolean(downloadLogicx.href && downloadLogicx.href.startsWith("blob:")),
    };
  };
}
