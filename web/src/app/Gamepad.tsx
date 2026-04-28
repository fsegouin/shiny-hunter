'use client';

import { useEffect, useRef } from 'react';
import type { Button as GbButton, WasmBoyEmulator } from '@/lib/emulator/wasmboy';

/**
 * On-screen Game Boy gamepad backed by `responsive-gamepad` — the same
 * input library WasmBoy.app uses. We don't roll our own pointer
 * handling: each button is registered via
 * `ResponsiveGamepad.TouchInput.addButtonInput(element, INPUT)` and
 * WasmBoy reads the joypad state from responsive-gamepad each frame
 * via `enableDefaultJoypad()`.
 *
 * Why not setJoypadState directly: a hand-rolled
 * pointerdown→setJoypadState→pointerup→setJoypadState pipeline races
 * the WasmBoy worker; quick taps can flip the joypad bit twice between
 * GB samplings and the game sees nothing. responsive-gamepad solves
 * this by maintaining persistent state that WasmBoy polls.
 *
 * NOTE: the parent must call `enableDefaultJoypad()` on the WasmBoy
 * instance before mounting this component, and disable it again (and
 * fall back to manual setJoypadState) when switching to headless mode.
 */

const BTN_STYLE: React.CSSProperties = {
  width: 56, height: 56, padding: 0,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 14, fontWeight: 600,
  touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none',
};

// Map our public Button names to responsive-gamepad input keys.
// D-pad buttons are DPAD_*, action buttons share names.
const RG_INPUT_KEY: Record<GbButton, string> = {
  UP: 'DPAD_UP',
  DOWN: 'DPAD_DOWN',
  LEFT: 'DPAD_LEFT',
  RIGHT: 'DPAD_RIGHT',
  A: 'A',
  B: 'B',
  START: 'START',
  SELECT: 'SELECT',
};

function PadButton({
  label,
  button,
  style,
}: {
  label: string;
  button: GbButton;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    let cancel: (() => void) | undefined;
    let mounted = true;
    (async () => {
      const { ResponsiveGamepad } = await import('responsive-gamepad');
      if (!mounted || !ref.current) return;
      const inputKey = RG_INPUT_KEY[button];
      const inputId = ResponsiveGamepad.RESPONSIVE_GAMEPAD_INPUTS[
        inputKey as keyof typeof ResponsiveGamepad.RESPONSIVE_GAMEPAD_INPUTS
      ];
      cancel = ResponsiveGamepad.TouchInput.addButtonInput(ref.current, inputId);
    })();
    return () => {
      mounted = false;
      cancel?.();
    };
  }, [button]);
  return (
    <button ref={ref} style={{ ...BTN_STYLE, ...style }}>
      {label}
    </button>
  );
}

export function Gamepad({ emu }: { emu: WasmBoyEmulator }) {
  // Suppress unused warning: the prop is here so consumers can keep
  // referencing the active emulator instance, but the gamepad itself
  // talks to responsive-gamepad via global state and doesn't need
  // per-button emu plumbing.
  void emu;
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto auto',
        gap: 24,
        alignItems: 'center',
        margin: '12px 0',
      }}
    >
      {/* D-pad */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 56px)',
          gridTemplateRows: 'repeat(3, 56px)',
          gap: 2,
        }}
      >
        <span />
        <PadButton label="↑" button="UP" />
        <span />
        <PadButton label="←" button="LEFT" />
        <span />
        <PadButton label="→" button="RIGHT" />
        <span />
        <PadButton label="↓" button="DOWN" />
        <span />
      </div>

      {/* A/B + Start/Select */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <PadButton label="B" button="B" style={{ background: '#421', color: '#fc6' }} />
          <PadButton label="A" button="A" style={{ background: '#421', color: '#fc6' }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <PadButton label="SELECT" button="SELECT" style={{ width: 80, fontSize: 11 }} />
          <PadButton label="START" button="START" style={{ width: 80, fontSize: 11 }} />
        </div>
      </div>
    </div>
  );
}
