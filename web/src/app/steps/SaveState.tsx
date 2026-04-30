'use client';

import { useCallback, useRef, useState } from 'react';
import { findBySha1, sha1OfBytes, type GameConfig } from '@/lib/games';
import { loadRomFromFile } from '@/lib/rom';
import { type WasmBoySaveState } from '@/lib/state';
import {
  init as initEmulator,
  type WasmBoyEmulator,
} from '@/lib/emulator/wasmboy';
import GameCanvas from '@/app/components/GameCanvas';
import { Gamepad } from '@/app/Gamepad';

interface Props {
  onComplete: (data: {
    romBytes: Uint8Array;
    config: GameConfig;
    savedState: WasmBoySaveState;
  }) => void;
}

type Status = 'idle' | 'loading-rom' | 'ready' | 'saving';

export default function SaveState({ onComplete }: Props) {
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [romBytes, setRomBytes] = useState<Uint8Array | null>(null);
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const onRomChosen = useCallback(async (file: File) => {
    setError(null);
    setStatus('loading-rom');

    // Load ROM bytes (handles .gb/.gbc and ZIP archives)
    let bytes: Uint8Array;
    try {
      const load = await loadRomFromFile(file);
      bytes = load.bytes;
    } catch (err) {
      setError(`Could not read ROM: ${(err as Error).message}`);
      setStatus('idle');
      return;
    }

    // Identify the ROM
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

    // Auto-init WasmBoy in windowed mode
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

      {/* ROM file input */}
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

      {/* Status / config info */}
      {status === 'loading-rom' && <p>Loading ROM and initializing emulator...</p>}
      {config && (
        <p className="ok">
          {config.game}/{config.region} &mdash; DV @
          0x{config.partyDvAddr.toString(16)}
        </p>
      )}

      {/* Error display */}
      {error && <p className="err">{error}</p>}

      {/* Canvas + Gamepad overlay */}
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

      {/* Save State button */}
      {status === 'ready' && (
        <div className="row">
          <button disabled={saving} onClick={onSaveState}>
            {saving ? 'Saving...' : 'Save State'}
          </button>
        </div>
      )}
    </section>
  );
}
