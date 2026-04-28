'use client';

import { useCallback, useRef, useState } from 'react';
import { decodeDVs, isShiny } from '@/lib/dv';
import { findBySha1, sha1OfBytes, type GameConfig } from '@/lib/games';
import { loadRomFromFile } from '@/lib/rom';
import { parseEventMacro, replayMacro, type EventMacro } from '@/lib/macro';
import { deserializeState, serializeState, type WasmBoySaveState } from '@/lib/state';
import {
  init as initEmulator,
  type WasmBoyEmulator,
} from '@/lib/emulator/wasmboy';
import { Gamepad } from './Gamepad';

function downloadBlob(filename: string, bytes: Uint8Array, mime = 'application/octet-stream') {
  const blob = new Blob([bytes as BlobPart], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

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
  const [macro, setMacro] = useState<EventMacro | null>(null);
  const [hasCheckpoint, setHasCheckpoint] = useState(false);
  const checkpointRef = useRef<WasmBoySaveState | null>(null);

  const append = (level: LogLine['level'], text: string) =>
    setLog((prev) => [...prev, { ts: Date.now(), level, text }]);

  const onRomChosen = useCallback(async (file: File) => {
    let load;
    try {
      load = await loadRomFromFile(file);
    } catch (err) {
      append('err', `could not read ROM: ${(err as Error).message}`);
      return;
    }
    const sha = await sha1OfBytes(load.bytes);
    setRomBytes(load.bytes);
    const cfg = findBySha1(sha) ?? null;
    setConfig(cfg);
    const sourceTag = load.source === 'zip' ? ` (extracted from ${file.name})` : '';
    append('info', `ROM: ${load.name}${sourceTag} (${load.bytes.byteLength.toLocaleString()} bytes)`);
    append(cfg ? 'ok' : 'err', `SHA-1: ${sha}${cfg ? ` → ${cfg.game}/${cfg.region}` : ' (unknown)'}`);
  }, []);

  const [mode, setMode] = useState<'idle' | 'headless' | 'windowed'>('idle');
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const stepInit = useCallback(async () => {
    if (!romBytes) return append('err', 'load a ROM first');
    setRunning(true);
    try {
      append('info', 'WasmBoy: initializing headless…');
      const t0 = performance.now();
      if (emu) await emu.shutdown();
      const e = await initEmulator({ rom: romBytes, mode: 'headless' });
      setEmu(e);
      setMode('headless');
      append('ok', `WasmBoy ready in ${(performance.now() - t0).toFixed(1)} ms`);
    } catch (err) {
      append('err', `init failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [romBytes, emu]);

  const stepInitWindowed = useCallback(async () => {
    if (!romBytes) return append('err', 'load a ROM first');
    if (!canvasRef.current) return append('err', 'canvas not yet mounted');
    setRunning(true);
    try {
      append('info', 'WasmBoy: initializing windowed (real-time)…');
      const t0 = performance.now();
      if (emu) await emu.shutdown();
      const e = await initEmulator({
        rom: romBytes,
        mode: 'windowed',
        canvas: canvasRef.current,
      });
      setEmu(e);
      setMode('windowed');
      append('ok', `windowed mode ready in ${(performance.now() - t0).toFixed(1)} ms — play to your checkpoint, then click "checkpoint here".`);
    } catch (err) {
      append('err', `init failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [romBytes, emu]);

  const captureCheckpointFromPlay = useCallback(async () => {
    if (!emu) return append('err', 'init in windowed mode first');
    setRunning(true);
    try {
      await emu.pause();
      const state = await emu.saveState();
      checkpointRef.current = state;
      setHasCheckpoint(true);
      const bytes = serializeState(state);
      const tag = config ? `${config.game}_${config.region}` : 'wasmboy';
      downloadBlob(`${tag}_${Date.now()}.wbst`, bytes);
      append('ok',
        `checkpoint captured + downloaded (${bytes.byteLength.toLocaleString()} bytes). ` +
        `Switch to headless mode to start hunting.`,
      );
      // Stay paused. User can click "resume" to keep playing if they
      // want to grab another checkpoint.
    } catch (err) {
      append('err', `checkpoint failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu, config]);

  const resumePlay = useCallback(async () => {
    if (!emu) return;
    try {
      await emu.play();
      append('info', 'resumed real-time playback');
    } catch (err) {
      append('err', `resume failed: ${(err as Error).message}`);
    }
  }, [emu]);

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
      const state = (await emu.saveState()) as WasmBoySaveState;
      const t1 = performance.now();
      checkpointRef.current = state;
      setHasCheckpoint(true);
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

  const downloadCheckpoint = useCallback(() => {
    if (!checkpointRef.current) return append('err', 'take a save state first');
    const bytes = serializeState(checkpointRef.current);
    const tag = config ? `${config.game}_${config.region}` : 'wasmboy';
    downloadBlob(`${tag}_${Date.now()}.wbst`, bytes);
    append('ok', `downloaded ${bytes.byteLength.toLocaleString()} bytes (.wbst)`);
  }, [config]);

  const onCheckpointFile = useCallback(async (file: File) => {
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const state = deserializeState(bytes);
      checkpointRef.current = state;
      setHasCheckpoint(true);
      append('ok', `loaded checkpoint from ${file.name} (${bytes.byteLength.toLocaleString()} bytes)`);
    } catch (err) {
      append('err', `could not load checkpoint: ${(err as Error).message}`);
    }
  }, []);

  const onMacroFile = useCallback(async (file: File) => {
    try {
      const text = await file.text();
      const m = parseEventMacro(JSON.parse(text));
      setMacro(m);
      append('ok',
        `loaded macro: ${m.events.length} events over ${m.totalFrames} frames` +
        (m.romSha1 ? ` · rom_sha1=${m.romSha1.slice(0, 12)}…` : ''),
      );
    } catch (err) {
      append('err', `could not parse macro: ${(err as Error).message}`);
    }
  }, []);

  const stepReplayMacro = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    if (!checkpointRef.current) return append('err', 'no checkpoint loaded — take or upload one');
    if (!macro) return append('err', 'no macro loaded — upload a .events.json');
    if (!config) return append('err', 'unknown ROM — no DV addr to read');
    setRunning(true);
    try {
      const t0 = performance.now();
      await emu.loadState(checkpointRef.current);
      emu.clearJoypad();
      await replayMacro(emu, macro);
      const dt = performance.now() - t0;

      const species = await emu.readByte(config.partySpeciesAddr);
      const speciesName = config.starters[species] ?? `unknown(0x${species.toString(16).padStart(2, '0')})`;
      const dvBytes = await emu.readBytes(config.partyDvAddr, 2);
      const dvs = decodeDVs(dvBytes[0], dvBytes[1]);
      const shiny = isShiny(dvs);
      append(
        shiny ? 'ok' : 'info',
        `replay: ${dt.toFixed(1)} ms · species=${speciesName} ` +
        `dvs=${JSON.stringify(dvs)}${shiny ? ' ★ SHINY' : ''}`,
      );
    } catch (err) {
      append('err', `replay failed: ${(err as Error).message}`);
    } finally {
      setRunning(false);
    }
  }, [emu, macro, config]);

  const stepReadDvAddr = useCallback(async () => {
    if (!emu) return append('err', 'init the emulator first');
    if (!config) return append('err', 'unknown ROM — no DV addr to read');
    setRunning(true);
    try {
      const bytes = await emu.readBytes(config.partyDvAddr, 2);
      const dvs = decodeDVs(bytes[0], bytes[1]);
      const species = await emu.readByte(config.partySpeciesAddr);
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
        await emu.loadState(checkpointRef.current!);
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
          // No `accept=` filter: some OSes don't register a MIME for .gb,
          // and the browser then greys out perfectly valid ROMs. We
          // validate by content (SHA-1 + ZIP magic) inside loadRomFromFile,
          // so accepting anything is safe.
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

      <h2>2. Bootstrap (play to checkpoint)</h2>
      <p className="muted">
        WasmBoy state files (.wbst) aren&apos;t interchangeable with PyBoy
        .state files, so the checkpoint has to be created here. Init
        windowed, play to the &quot;Do you want this Pokémon?&quot; YES
        prompt with the on-screen buttons, then click <b>checkpoint here</b>.
        The .wbst downloads automatically and stays in memory for the
        macro-replay flow below.
      </p>
      <div className="row">
        <button disabled={!romBytes || running} onClick={stepInitWindowed}>
          init windowed
        </button>
        <button disabled={mode !== 'windowed' || running} onClick={resumePlay}>
          resume play
        </button>
        <button disabled={mode !== 'windowed' || running} onClick={captureCheckpointFromPlay}>
          checkpoint here (pause + download .wbst)
        </button>
      </div>
      <div
        style={{
          position: 'relative',
          display: mode === 'windowed' ? 'block' : 'none',
          width: '100%',
          maxWidth: 720,
          aspectRatio: '160 / 144',
          background: '#000',
          border: '1px solid #333',
          margin: '12px auto',
        }}
      >
        <canvas
          ref={canvasRef}
          width={160}
          height={144}
          className="emu-canvas"
        />
        {mode === 'windowed' && emu && <Gamepad emu={emu} />}
      </div>

      <h2>3. Steps</h2>
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

      <h2>4. Macro replay (load state → replay → read DVs)</h2>
      <p className="muted">
        Take or upload a checkpoint, upload a `.events.json` recorded by the
        Python `shiny-hunt record` command, then replay. The DVs after
        replay land in the party at the configured address — that's what
        the hunter loop will read on every attempt.
      </p>
      <div className="row">
        <label>checkpoint:</label>
        <input
          type="file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onCheckpointFile(f);
          }}
        />
        <button disabled={!hasCheckpoint || running} onClick={downloadCheckpoint}>
          download current checkpoint (.wbst)
        </button>
      </div>
      <div className="row">
        <label>macro:</label>
        <input
          type="file"
          accept=".json,application/json"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void onMacroFile(f);
          }}
        />
        {macro && (
          <span className="ok">
            {macro.events.length} events · {macro.totalFrames} frames
          </span>
        )}
      </div>
      <div className="row">
        <button
          disabled={!emu || !hasCheckpoint || !macro || !config || running}
          onClick={stepReplayMacro}
        >
          load state + replay macro + read DVs
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
