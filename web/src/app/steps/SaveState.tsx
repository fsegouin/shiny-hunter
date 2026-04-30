'use client';

import { useCallback, useRef, useState } from 'react';
import { findBySha1, sha1OfBytes, type GameConfig } from '@/lib/games';
import { loadRomFromFile } from '@/lib/rom';
import { type WasmBoySaveState } from '@/lib/state';
import {
  init as initEmulator,
  type WasmBoyEmulator,
} from '@/lib/emulator/wasmboy';
import { loadCheckpoint, type Checkpoint } from '@/lib/storage';
import GameCanvas from '@/app/components/GameCanvas';
import { Gamepad } from '@/app/Gamepad';

interface Props {
  onComplete: (data: {
    romBytes: Uint8Array;
    config: GameConfig;
    savedState: WasmBoySaveState;
  }) => void;
  onRestoreCheckpoint?: (data: {
    romBytes: Uint8Array;
    config: GameConfig;
    checkpoint: Checkpoint;
  }) => void;
}

type Status = 'idle' | 'loading-rom' | 'has-checkpoint' | 'ready' | 'saving';

export default function SaveState({ onComplete, onRestoreCheckpoint }: Props) {
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [romBytes, setRomBytes] = useState<Uint8Array | null>(null);
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [existingCheckpoint, setExistingCheckpoint] = useState<Checkpoint | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const startEmulator = useCallback(async (bytes: Uint8Array, cfg: GameConfig) => {
    const canvas = canvasRef.current;
    if (!canvas) {
      setError('Canvas not available. Please try again.');
      setStatus('idle');
      return;
    }
    try {
      const e = await initEmulator({
        rom: bytes,
        mode: 'windowed',
        canvas,
      });
      setEmu(e);
      setStatus('ready');
    } catch (err) {
      setError(`Emulator init failed: ${(err as Error).message}`);
      setStatus('idle');
    }
  }, []);

  const onRomChosen = useCallback(async (file: File) => {
    setError(null);
    setStatus('loading-rom');

    let bytes: Uint8Array;
    try {
      const load = await loadRomFromFile(file);
      bytes = load.bytes;
    } catch (err) {
      setError(`Could not read ROM: ${(err as Error).message}`);
      setStatus('idle');
      return;
    }

    const sha = await sha1OfBytes(bytes);
    const cfg = findBySha1(sha);
    if (!cfg) {
      setError(
        `Unrecognised ROM (SHA-1: ${sha}). Only supported Gen 1 ROMs are accepted.`,
      );
      setStatus('idle');
      return;
    }

    setRomBytes(bytes);
    setConfig(cfg);

    const cp = await loadCheckpoint(cfg.game, cfg.region);
    if (cp) {
      setExistingCheckpoint(cp);
      setStatus('has-checkpoint');
      return;
    }

    await startEmulator(bytes, cfg);
  }, [startEmulator]);

  const useExistingCheckpoint = useCallback(() => {
    if (!existingCheckpoint || !romBytes || !config) return;
    if (onRestoreCheckpoint) {
      onRestoreCheckpoint({ romBytes, config, checkpoint: existingCheckpoint });
    } else {
      onComplete({ romBytes, config, savedState: existingCheckpoint.savedState });
    }
  }, [existingCheckpoint, romBytes, config, onComplete, onRestoreCheckpoint]);

  const startFresh = useCallback(async () => {
    if (!romBytes || !config) return;
    setExistingCheckpoint(null);
    await startEmulator(romBytes, config);
  }, [romBytes, config, startEmulator]);

  const onSaveState = useCallback(async () => {
    if (!emu || !romBytes || !config) return;
    setSaving(true);
    try {
      await emu.pause();
      const savedState = await emu.saveState();
      onComplete({ romBytes, config, savedState });
    } catch (err) {
      setError(`Save state failed: ${(err as Error).message}`);
      setSaving(false);
    }
  }, [emu, romBytes, config, onComplete]);

  const showCanvas = status === 'ready' || status === 'loading-rom';

  return (
    <section>
      <h2>Step 1 &mdash; Load ROM &amp; create checkpoint</h2>
      <p className="muted">
        Select a Gen 1 ROM (.gb or .zip). Play to the &ldquo;Do you want this
        Pok&eacute;mon?&rdquo; YES/NO dialog, then click <b>Save State</b>.
      </p>

      {status === 'idle' && (
        <div className="row">
          <input
            type="file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onRomChosen(f);
            }}
          />
        </div>
      )}

      {status === 'loading-rom' && <p>Loading ROM and initializing emulator...</p>}

      {status === 'has-checkpoint' && existingCheckpoint && config && (
        <div>
          <p className="ok">
            {config.game}/{config.region} &mdash; existing checkpoint found
            ({new Date(existingCheckpoint.date).toLocaleDateString()}
            {existingCheckpoint.macro ? ', with macro' : ''})
          </p>
          <div className="row">
            <button onClick={useExistingCheckpoint}>
              Use existing checkpoint
              {existingCheckpoint.macro
                ? ` (skip to ${existingCheckpoint.verifiedSpecies ? 'Hunt' : 'Record Macro'})`
                : ''}
            </button>
            <button onClick={() => void startFresh()}>Start fresh</button>
          </div>
        </div>
      )}

      {config && status !== 'has-checkpoint' && (
        <p className="ok">
          {config.game}/{config.region} &mdash; DV @
          0x{config.partyDvAddr.toString(16)}
        </p>
      )}

      {error && <p className="err">{error}</p>}

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
        {status === 'ready' && emu && <Gamepad emu={emu} />}
      </div>

      {status === 'ready' && (
        <div className="row">
          {[1, 2, 3].map((s) => (
            <button
              key={s}
              className={speed === s ? 'speed-active' : ''}
              onClick={() => { setSpeed(s); emu?.setSpeed(s); }}
            >
              {s}x
            </button>
          ))}
          <button disabled={saving} onClick={onSaveState}>
            {saving ? 'Saving...' : 'Save State'}
          </button>
        </div>
      )}
    </section>
  );
}
