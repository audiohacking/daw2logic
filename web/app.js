/**
 * Browser runner for the py2wasm-compiled daw2logic module.
 *
 * Wire format (stdout): u32 notes_len LE, u32 zip_len LE, notes utf-8, zip bytes.
 */

import { init, Wasmer } from "https://cdn.jsdelivr.net/npm/@wasmer/sdk@0.9.0/dist/index.mjs";

const WASM_URL = new URL("./wasm/daw2logic.wasm", import.meta.url);
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

function concatUint8(chunks) {
  const total = chunks.reduce((sum, part) => sum + part.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of chunks) {
    out.set(part, offset);
    offset += part.byteLength;
  }
  return out;
}

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

async function ensureRuntime() {
  if (!runtimeReady) {
    runtimeReady = (async () => {
      setStatus("Loading WebAssembly runtime…");
      await init({ module: SDK_WASM_URL });
      const response = await fetch(WASM_URL);
      if (!response.ok) {
        throw new Error(
          `WASM module not found (${response.status}). Build with scripts/build_wasm.sh or wait for the GitHub Pages workflow.`
        );
      }
      return new Uint8Array(await response.arrayBuffer());
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
  const wasmBytes = await ensureRuntime();
  setStatus("Converting…");

  const pkg = await Wasmer.fromFile(wasmBytes);
  if (!pkg.entrypoint) {
    throw new Error("compiled module has no WASI entrypoint");
  }

  const stdoutChunks = [];
  const stderrChunks = [];
  const instance = await pkg.entrypoint.run({ stdin: inputBytes });
  await instance.stdout?.pipeTo(
    new WritableStream({
      write(chunk) {
        stdoutChunks.push(chunk);
      },
    })
  );
  await instance.stderr?.pipeTo(
    new WritableStream({
      write(chunk) {
        stderrChunks.push(new TextDecoder().decode(chunk));
      },
    })
  );

  const outcome = await instance.wait();
  if (!outcome.ok) {
    const errText = stderrChunks.join("").trim();
    throw new Error(errText || `converter exited with code ${outcome.code}`);
  }

  const stdout = concatUint8(stdoutChunks);
  if (stdout.byteLength === 0) {
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
