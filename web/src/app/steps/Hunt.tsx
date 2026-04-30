'use client';

import { useCallback, useRef, useState, useEffect } from 'react';
import type { WasmBoySaveState } from '@/lib/state';
import type { GameConfig } from '@/lib/games';
import type { EventMacro } from '@/lib/macro';
import {
  startHunt,
  transferToWasmBoyState,
  type HuntHandle,
  type HuntCallbacks,
} from '@/lib/hunt';
import { init as initEmulator, type WasmBoyEmulator } from '@/lib/emulator/wasmboy';
import { preloadFont, renderTextbox, GB_SCREEN_TILES_W, SHINY_CHAR } from '@/lib/gbfont';
import ShinyResult from '../components/ShinyResult';
import { Gamepad } from '../Gamepad';

interface Props {
  romBytes: Uint8Array;
  config: GameConfig;
  savedState: WasmBoySaveState;
  macro: EventMacro;
}

type Phase = 'ready' | 'hunting' | 'paused-shiny' | 'done';

interface ShinyInfo {
  speciesName: string;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  attempt: number;
  delay: number;
  state: WasmBoySaveState;
}

function downloadBlob(filename: string, bytes: Uint8Array, mime = 'application/octet-stream') {
  const blob = new Blob([bytes as BlobPart], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Format seconds as HH:MM:SS. */
function fmtTime(secs: number): string {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = Math.floor(secs % 60);
  return [h, m, s].map((v) => String(v).padStart(2, '0')).join(':');
}

const DELAY_WINDOW = 1 << 16; // 65 536

function pad(n: number, width: number): string {
  return String(n).padStart(width, ' ');
}

interface OverlayInfo {
  attempt: number;
  speciesName: string;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  shiny: boolean;
}

function buildOverlayLines(o: OverlayInfo): string[] {
  const lines = [
    `#${o.attempt} ${o.speciesName.toUpperCase()}`,
    `ATK ${pad(o.dvs.atk, 2)} DEF ${pad(o.dvs.def, 2)}`,
    `SPD ${pad(o.dvs.spd, 2)} SPC ${pad(o.dvs.spc, 2)} HP${pad(o.dvs.hp, 2)}`,
  ];
  if (o.shiny) lines.push(`${SHINY_CHAR}SHINY!`);
  return lines;
}

/** Convert worker RGB (3 bpp) pixels to canvas RGBA ImageData. */
function rgbToImageData(rgb: Uint8Array, width: number, height: number): ImageData {
  const rgba = new Uint8ClampedArray(width * height * 4);
  const pixelCount = width * height;
  for (let i = 0; i < pixelCount; i++) {
    const srcOff = i * 3;
    const dstOff = i * 4;
    rgba[dstOff] = rgb[srcOff];
    rgba[dstOff + 1] = rgb[srcOff + 1];
    rgba[dstOff + 2] = rgb[srcOff + 2];
    rgba[dstOff + 3] = 255;
  }
  return new ImageData(rgba, width, height);
}

export default function Hunt({ romBytes, config, savedState, macro }: Props) {
  const [phase, setPhase] = useState<Phase>('ready');
  const [error, setError] = useState<string | null>(null);
  const [attempts, setAttempts] = useState(0);
  const [speed, setSpeed] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [shiny, setShiny] = useState<ShinyInfo | null>(null);
  const [shinies, setShinies] = useState<ShinyInfo[]>([]);
  const [doneInfo, setDoneInfo] = useState<{ total: number; found: number } | null>(null);
  const [playingShiny, setPlayingShiny] = useState(false);

  const handleRef = useRef<HuntHandle | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const emuRef = useRef<WasmBoyEmulator | null>(null);
  const t0Ref = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Preload the GB font tiles so the first overlay renders without delay.
  useEffect(() => { void preloadFont(); }, []);

  // Elapsed timer — ticks every second while hunting
  useEffect(() => {
    if (phase === 'hunting') {
      timerRef.current = setInterval(() => {
        setElapsed((performance.now() - t0Ref.current) / 1000);
      }, 1000);
    }
    return () => {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [phase]);

  /**
   * Draw the framebuffer onto the preview canvas, optionally overlaying
   * the Pokémon-style textbox for the latest attempt.
   */
  const drawFrame = useCallback(async (pixels: Uint8Array, overlay: OverlayInfo | null) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.imageSmoothingEnabled = false;
    const imageData = rgbToImageData(pixels, 160, 144);
    ctx.putImageData(imageData, 0, 0);
    if (!overlay) return;
    const textbox = await renderTextbox(buildOverlayLines(overlay), GB_SCREEN_TILES_W);
    if (canvasRef.current !== canvas) return; // canvas swapped, abort
    ctx.drawImage(textbox, 0, 0);
  }, []);

  /** Start the hunt. */
  const startHunting = useCallback(() => {
    setPhase('hunting');
    setError(null);
    setAttempts(0);
    setSpeed(0);
    setShiny(null);
    setShinies([]);
    setDoneInfo(null);
    setPlayingShiny(false);
    t0Ref.current = performance.now();

    const callbacks: HuntCallbacks = {
      onProgress(data) {
        setAttempts(data.attempt);
        setSpeed(data.attemptsPerSec);
        setElapsed((performance.now() - t0Ref.current) / 1000);

        const speciesName =
          config.starters[data.latestSpecies] ??
          `species(0x${data.latestSpecies.toString(16)})`;
        void drawFrame(data.pixels, {
          attempt: data.attempt,
          speciesName,
          dvs: data.latestDvs,
          shiny: data.shiny,
        });
      },
      onShiny(data) {
        const wbState = transferToWasmBoyState(data.state);
        const speciesName =
          config.starters[data.species] ??
          `species(0x${data.species.toString(16)})`;

        const info: ShinyInfo = {
          speciesName,
          dvs: data.dvs,
          attempt: data.attempt,
          delay: data.delay,
          state: wbState,
        };

        setShiny(info);
        setShinies((prev) => [...prev, info]);
        setPhase('paused-shiny');
      },
      onDone(data) {
        setDoneInfo({ total: data.totalAttempts, found: data.shiniesFound });
        setPhase('done');
      },
      onError(message) {
        setError(message);
        setPhase('done');
      },
    };

    const handle = startHunt(romBytes, savedState, macro, config, callbacks);
    handleRef.current = handle;
  }, [romBytes, savedState, macro, config, drawFrame]);

  /** Stop the hunt and terminate the worker. */
  const stopHunting = useCallback(() => {
    handleRef.current?.terminate();
    handleRef.current = null;
    setPhase('done');
    setDoneInfo({ total: attempts, found: shinies.length });
  }, [attempts, shinies.length]);

  /** Play the shiny state in the emulator on the preview canvas. */
  const playShiny = useCallback(async () => {
    if (!shiny) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    setPlayingShiny(true);
    try {
      // Shut down any existing emulator
      if (emuRef.current) {
        await emuRef.current.shutdown();
        emuRef.current = null;
      }

      const emu = await initEmulator({
        rom: romBytes,
        mode: 'windowed',
        canvas,
      });
      await emu.loadState(shiny.state);
      emuRef.current = emu;
    } catch (err) {
      setError(`Play failed: ${(err as Error).message}`);
      setPlayingShiny(false);
    }
  }, [shiny, romBytes]);

  /** Download the .sav (SRAM dump) for the shiny state. */
  const downloadSav = useCallback(async () => {
    if (!shiny) return;

    try {
      // Initialise a headless emulator, load the shiny state, dump SRAM
      const emu = await initEmulator({ rom: romBytes, mode: 'headless' });
      await emu.loadState(shiny.state);
      const sram = await emu.dumpSram();
      await emu.shutdown();

      const tag = `${config.game}_${config.region}_shiny_${shiny.speciesName}`;
      downloadBlob(`${tag}.sav`, sram);
    } catch (err) {
      setError(`Download failed: ${(err as Error).message}`);
    }
  }, [shiny, romBytes, config]);

  /** Keep scanning: shut down windowed emulator, resume the worker. */
  const keepScanning = useCallback(async () => {
    // Shut down any windowed emulator from "Play"
    if (emuRef.current) {
      await emuRef.current.shutdown();
      emuRef.current = null;
    }
    setPlayingShiny(false);
    setShiny(null);
    setPhase('hunting');
    handleRef.current?.resume();
  }, []);

  // Clean up worker and emulator on unmount
  useEffect(() => {
    return () => {
      handleRef.current?.terminate();
      // Fire-and-forget shutdown — can't await in a cleanup function
      emuRef.current?.shutdown();
    };
  }, []);

  const estimated =
    speed > 0 ? ((DELAY_WINDOW - attempts) / speed) : 0;

  return (
    <section>
      <h2>Step 3 &mdash; Hunt</h2>
      <p className="muted">
        Scanning {DELAY_WINDOW.toLocaleString()} delay frames for a shiny{' '}
        {Object.values(config.starters).join('/')}.
      </p>

      {error && <p className="err">{error}</p>}

      {/* Ready state — show the Hunt button */}
      {phase === 'ready' && (
        <div className="row">
          <button onClick={startHunting}>Hunt!</button>
        </div>
      )}

      {/* Stats bar — visible while hunting, paused on shiny, or done */}
      {phase !== 'ready' && (
        <div className="stats-bar">
          <span>Attempts: {attempts.toLocaleString()}</span>
          <span>Speed: {speed.toFixed(1)}/s</span>
          <span>Elapsed: {fmtTime(elapsed)}</span>
          {phase === 'hunting' && speed > 0 && (
            <span>ETA: {fmtTime(estimated)}</span>
          )}
          <span>Shinies: {shinies.length}</span>
        </div>
      )}

      {/* Stop button while hunting */}
      {phase === 'hunting' && (
        <div className="row">
          <button onClick={stopHunting}>Stop</button>
        </div>
      )}

      {/* Preview canvas — a single persistent canvas element so the ref
          stays stable across headless-preview / windowed-play transitions. */}
      <div
        className="preview-wrap"
        style={{
          display: phase !== 'ready' ? 'block' : 'none',
          position: 'relative',
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
          className="emu-canvas"
          width={160}
          height={144}
        />
        {playingShiny && emuRef.current && (
          <Gamepad emu={emuRef.current} />
        )}
      </div>

      {/* Shiny result panel */}
      {phase === 'paused-shiny' && shiny && (
        <ShinyResult
          speciesName={shiny.speciesName}
          dvs={shiny.dvs}
          attempt={shiny.attempt}
          delay={shiny.delay}
          onPlay={playShiny}
          onDownloadSav={downloadSav}
          onKeepScanning={keepScanning}
        />
      )}

      {/* Completion message */}
      {phase === 'done' && doneInfo && (
        <div>
          <p className="ok">
            Scan complete: {doneInfo.total.toLocaleString()} attempts,{' '}
            {doneInfo.found} {doneInfo.found === 1 ? 'shiny' : 'shinies'} found.
          </p>
          {shinies.length > 0 && (
            <div>
              <h3>All shinies found:</h3>
              {shinies.map((s, i) => (
                <div key={i} className="stats-bar">
                  <span className="ok">{s.speciesName}</span>
                  <span>ATK {s.dvs.atk}</span>
                  <span>DEF {s.dvs.def}</span>
                  <span>SPD {s.dvs.spd}</span>
                  <span>SPC {s.dvs.spc}</span>
                  <span>HP {s.dvs.hp}</span>
                  <span className="muted">delay {s.delay}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
