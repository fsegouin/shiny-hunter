'use client';

import { useCallback, useRef, useState } from 'react';
import {
  init as initEmulator,
  type WasmBoyEmulator,
} from '@/lib/emulator/wasmboy';
import type { WasmBoySaveState } from '@/lib/state';
import type { GameConfig } from '@/lib/games';
import type { EventMacro } from '@/lib/macro';
import { isShiny } from '@/lib/dv';
import { verifyMacro } from '@/lib/verify';
import { startRecording, type RecordingSession } from '@/lib/recorder';
import GameCanvas from '@/app/components/GameCanvas';
import { Gamepad } from '@/app/Gamepad';

interface Props {
  romBytes: Uint8Array;
  config: GameConfig;
  savedState: WasmBoySaveState;
  onComplete: (macro: EventMacro, verifiedSpecies: string) => void;
}

type Phase = 'init' | 'recording' | 'verifying' | 'verified' | 'error';

export default function RecordMacro({ romBytes, config, savedState, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>('init');
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [error, setError] = useState('');
  const [verifyInfo, setVerifyInfo] = useState('');
  const [speed, setSpeed] = useState(1);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sessionRef = useRef<RecordingSession | null>(null);
  const macroRef = useRef<EventMacro | null>(null);
  const speciesRef = useRef('');

  const startRecordingFlow = useCallback(async () => {
    if (!canvasRef.current) return;
    setError('');
    try {
      const e = await initEmulator({
        rom: romBytes,
        mode: 'windowed',
        canvas: canvasRef.current,
      });
      await e.loadState(savedState);
      setEmu(e);

      const rec = startRecording(e);
      sessionRef.current = rec;
      setPhase('recording');
    } catch (err) {
      setError((err as Error).message);
      setPhase('error');
    }
  }, [romBytes, savedState]);

  const stopRecording = useCallback(async () => {
    if (!sessionRef.current || !emu) return;
    setPhase('verifying');
    const macro = await sessionRef.current.stop();
    macroRef.current = macro;

    // Verify using the bare WASM worker (same one the hunt uses).
    // WasmBoy's singleton worker is left in a broken state after the
    // recorder's manual _runWasmExport calls — its postMessage wrapper
    // times out on SET_MEMORY. The bare WASM worker has its own
    // independent WASM instance and avoids WasmBoy entirely.
    try {
      const { species, dvs } = await verifyMacro(romBytes, savedState, macro, config);

      if (species === 0) {
        setError(
          `Macro didn't capture the Pokémon (species=0, dvs=${JSON.stringify(dvs)}). ` +
          `Macro had ${macro.events.length} events over ${macro.totalFrames} frames. Try recording again.`
        );
        setPhase('error');
        return;
      }

      const name = config.starters[species] ?? `species(0x${species.toString(16)})`;
      const shinyTag = isShiny(dvs) ? ' (shiny!)' : '';
      speciesRef.current = name;
      setVerifyInfo(
        `${macro.events.length} events, ${macro.totalFrames} frames — ` +
        `verified: ${name} ATK=${dvs.atk} DEF=${dvs.def} SPD=${dvs.spd} SPC=${dvs.spc}${shinyTag}`,
      );
      setPhase('verified');
    } catch (err) {
      console.error('Verify error:', err);
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Verify failed: ${msg}`);
      setPhase('error');
    }
  }, [emu, romBytes, savedState, config]);

  const confirm = useCallback(() => {
    if (macroRef.current) {
      onComplete(macroRef.current, speciesRef.current);
    }
  }, [onComplete]);

  const showCanvas = phase === 'recording';

  return (
    <section>
      <h2>Step 2 &mdash; Record Macro</h2>
      <p className="muted">
        Accept the Pok&eacute;mon using the on-screen buttons, then click
        {' '}<b>Done</b>.
      </p>

      {error && <p className="err">{error}</p>}

      {phase === 'init' && (
        <button onClick={startRecordingFlow}>Start Recording</button>
      )}

      <div
        style={{
          position: 'relative',
          display: showCanvas ? 'block' : 'none',
          width: '100%',
          maxWidth: 720,
          aspectRatio: '160 / 144',
          background: '#000',
          border: '1px solid #333',
          margin: '12px auto',
        }}
      >
        <GameCanvas ref={canvasRef} visible={showCanvas} />
        {phase === 'recording' && emu && <Gamepad emu={emu} />}
      </div>

      {phase === 'recording' && (
        <div className="row" style={{ marginTop: 12 }}>
          <span className="recording-indicator">REC</span>
          {[1, 2, 3].map((s) => (
            <button
              key={s}
              className={speed === s ? 'speed-active' : ''}
              onClick={() => { setSpeed(s); emu?.setSpeed(s); }}
            >
              {s}x
            </button>
          ))}
          <button onClick={stopRecording}>Done</button>
        </div>
      )}

      {phase === 'verifying' && <p>Verifying macro&hellip;</p>}

      {phase === 'verified' && (
        <div>
          <p className="ok">{verifyInfo}</p>
          <button onClick={confirm}>Continue to Hunt</button>
        </div>
      )}

      {phase === 'error' && (
        <button onClick={startRecordingFlow}>Re-record</button>
      )}
    </section>
  );
}
