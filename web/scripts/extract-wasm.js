/**
 * Extract the embedded WASM binary from WasmBoy's worker file and save it
 * as a standalone static asset. This lets our own Web Worker load the WASM
 * directly via fetch() instead of relying on WasmBoy's internal base64 blob.
 *
 * Runs automatically via the "postinstall" npm script.
 */

const fs = require("fs");
const path = require("path");

const WORKER_PATH = path.join(
  __dirname,
  "..",
  "node_modules",
  "wasmboy",
  "dist",
  "worker",
  "wasmboy.wasm.worker.js"
);
const OUTPUT_PATH = path.join(__dirname, "..", "public", "wasmboy-core.wasm");

const workerSrc = fs.readFileSync(WORKER_PATH, "utf8");

const match = workerSrc.match(/data:application\/wasm;base64,([A-Za-z0-9+/=]+)/);
if (!match) {
  console.error("ERROR: Could not find base64-encoded WASM in", WORKER_PATH);
  process.exit(1);
}

const wasmBytes = Buffer.from(match[1], "base64");

// Verify WASM magic bytes: \0asm
const WASM_MAGIC = Buffer.from([0x00, 0x61, 0x73, 0x6d]);
if (!wasmBytes.subarray(0, 4).equals(WASM_MAGIC)) {
  console.error(
    "ERROR: Decoded binary does not start with WASM magic bytes (\\0asm)"
  );
  process.exit(1);
}

fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
fs.writeFileSync(OUTPUT_PATH, wasmBytes);

console.log(
  `Extracted WasmBoy WASM binary (${wasmBytes.length} bytes) -> ${OUTPUT_PATH}`
);
