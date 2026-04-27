'use client';

import { useCallback, useRef, useState } from 'react';
import { decodeDVs, isShiny } from '@/lib/dv';
import { findBySha1, sha1OfBytes, type GameConfig } from '@/lib/games';
import {
  init as initEmulator,
  type WasmBoyEmulator,
} from '@/lib/emulator/wasmboy';

interface LogLine {
  ts: number;
  level: 'info' | 'ok' | 'err';
  text: string;
}

/**
 * WasmBoy spike: drop in a ROM and exercise every primitive the hunter
 * loop needs. Each button corresponds to one verification step. The log
 * panel doubles as the spike's report.
 */
export default function SpikePage() {
  const [log, setLog] = useState<LogLine[]>([]);
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [romBytes, setRomBytes] = useState<Uint8Array | null>(null);
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [running, setRunning] = useState(false);
  const checkpointRef = useRef<unknown>(null);

  const append = (level: LogLine['level'], text: string) =>
    setLog((prev) => [...prev, { ts: Date.now(), level, text }]);

  const onRomChosen = useCallback(async (file: File) => {
    const buf = new Uint8Array(await file.arrayBuffer());
    const sha = await sha1OfBytes(buf);
    setRomBytes(buf);
    const cfg = findBySha1(sha) ?? null;
    setConfig(cfg);
    append('info', `ROM: ${file.name} (${buf.byteLength.toLocaleString()} bytes)`);
    append(cfg ? 'ok' : 'err', `SHA-1: ${sha}${cfg ? ` → ${cfg.game}/${cfg.region}` : ' (unknown)'}`);
  }, []);

  const stepInit = useCallback(async () => {
    if (!romBytes) return append('err', 'load a ROM first');
    setRunning(true);
    try {
      append('info', 'WasmBoy: initializing headless…');
      const t0 = performance.now();
      const e = await initEmulator({ rom: romBytes, headless: true });
      setEmu(e);
      append('ok', `WasmBoy ready in ${(performance.now() - t0).toFixed(1)} ms`);
    } catch (err) {
      append('err', `init failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [romBytes]);

  const stepTickBenchmark = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    setRunning(true);
    try {
      const FRAMES = 600; // 10 seconds of GB time
      const t0 = performance.now();
      await emu.tick(FRAMES);
      const dt = performance.now() - t0;
      const realtime = (FRAMES * (1000 / 60)) / dt;
      append(
        'ok',
        `tick(${FRAMES}) took ${dt.toFixed(1)} ms — ${realtime.toFixed(1)}× realtime`,
      );
    } catch (err) {
      append('err', `tick failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu]);

  const stepSaveStateRoundTrip = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    setRunning(true);
    try {
      const t0 = performance.now();
      const state = await emu.saveState();
      const t1 = performance.now();
      checkpointRef.current = state;
      append('ok', `saveState in ${(t1 - t0).toFixed(2)} ms`);
      const t2 = performance.now();
      await emu.loadState(state);
      const t3 = performance.now();
      append('ok', `loadState in ${(t3 - t2).toFixed(2)} ms`);
    } catch (err) {
      append('err', `state I/O failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu]);

  const stepReadDvAddr = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    if (!config) return append('err', 'unknown ROM — no DV addr to read');
    setRunning(true);
    try {
      const bytes = emu.readBytes(config.partyDvAddr, 2);
      const dvs = decodeDVs(bytes[0], bytes[1]);
      const species = emu.readByte(config.partySpeciesAddr);
      append(
        'info',
        `species=0x${species.toString(16).padStart(2, '0')} ` +
          `dvs=${JSON.stringify(dvs)} shiny=${isShiny(dvs)}`,
      );
      append(
        'info',
        `(this almost certainly looks like garbage; we're not yet at a real DV write)`,
      );
    } catch (err) {
      append('err', `readBytes failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu, config]);

  const stepDumpSram = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    setRunning(true);
    try {
      const t0 = performance.now();
      const sram = await emu.dumpSram();
      append(
        'ok',
        `dumpSram: ${sram.byteLength.toLocaleString()} bytes in ${(
          performance.now() - t0
        ).toFixed(1)} ms`,
      );
    } catch (err) {
      append('err', `dumpSram failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu]);

  const stepDeterminism = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    if (!config) return append('err', 'unknown ROM');
    if (!checkpointRef.current) return append('err', 'take a save-state first (button 3)');
    setRunning(true);
    try {
      // Run forward identical # of frames twice from the same state; the
      // bytes at partyDvAddr should match. Confirms PyBoy-style determinism.
      const ADV = 200;
      const runFromState = async () => {
        await emu.loadState(checkpointRef.current);
        await emu.tick(ADV);
        return emu.readBytes(config.partyDvAddr, 2);
      };
      const a = await runFromState();
      const b = await runFromState();
      const equal = a[0] === b[0] && a[1] === b[1];
      append(equal ? 'ok' : 'err', `determinism check after ${ADV} frames: ${equal ? 'PASS' : 'FAIL'}`);
    } catch (err) {
      append('err', `determinism check failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu, config]);

  return (
    <main>
      <h1>shiny-hunter web — WasmBoy spike</h1>
      <p className="muted">
        Drop a Pokémon Gen 1 ROM and run each step. Goal: confirm WasmBoy can
        do everything the hunter loop needs (load, save/load state, fast
        headless ticking, RAM reads at GB addresses, SRAM dump, determinism).
        ROM stays in the browser; nothing is uploaded.
      </p>

      <h2>1. ROM</h2>
      <div className="row">
        <input
          type="file"
          accept=".gb,.gbc,.zip"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onRomChosen(f);
          }}
        />
        {config && (
          <span className="ok">
            {config.game}/{config.region} · DV @ 0x{config.partyDvAddr.toString(16)}
          </span>
        )}
      </div>

      <h2>2. Steps</h2>
      <div className="row">
        <button disabled={!romBytes || running} onClick={stepInit}>
          init emulator
        </button>
        <button disabled={!emu || running} onClick={stepTickBenchmark}>
          tick(600) benchmark
        </button>
        <button disabled={!emu || running} onClick={stepSaveStateRoundTrip}>
          saveState / loadState
        </button>
        <button disabled={!emu || running} onClick={stepReadDvAddr}>
          read DV addr
        </button>
        <button disabled={!emu || running} onClick={stepDumpSram}>
          dump SRAM
        </button>
        <button disabled={!emu || running} onClick={stepDeterminism}>
          determinism check
        </button>
      </div>

      <h2>Log</h2>
      <pre>
        {log.length === 0 ? '(no events yet)' :
          log.map((l, i) => (
            <span key={i} className={l.level}>
              {new Date(l.ts).toISOString().slice(11, 23)} · {l.text}
              {'\n'}
            </span>
          ))}
      </pre>
    </main>
  );
}
