'use client';

import { useCallback, useRef } from 'react';
import type { Button as GbButton, WasmBoyEmulator } from '@/lib/emulator/wasmboy';

// Game Boy frames at 60 Hz. WasmBoy runs in a worker, and our
// setJoypadState calls post messages to it; a too-fast press+release
// can let both messages arrive between two GB joypad samplings and
// the game sees nothing. Hold every press for at least this many ms
// to guarantee at least a few frames of "down" state. 80 ms ≈ 5 frames,
// which is well above any GB input handler's debounce.
const MIN_HOLD_MS = 80;

/**
 * On-screen Game Boy gamepad. Each button uses pointer events so it
 * works on touch (iPhone), mouse, and stylus. `touchAction: 'none'`
 * stops the page from scrolling while the user is mashing buttons.
 */

const BTN_STYLE: React.CSSProperties = {
  width: 56, height: 56, padding: 0,
  display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontSize: 14, fontWeight: 600,
  touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none',
};

function PadButton({
  label,
  emu,
  button,
  style,
}: {
  label: string;
  emu: WasmBoyEmulator;
  button: GbButton;
  style?: React.CSSProperties;
}) {
  const releaseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pressedAt = useRef(0);

  const press = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      e.preventDefault();
      try {
        // Capture so pointermove/up/cancel keep firing on this button
        // even if the finger drifts. NOTE: pointerleave still fires on
        // the actual hit-test geometry regardless of capture, which is
        // why we deliberately don't bind it — small wobbles would
        // release the button mid-press.
        e.currentTarget.setPointerCapture(e.pointerId);
      } catch {
        // setPointerCapture can throw on certain browsers if the
        // pointer is no longer active; safe to ignore.
      }
      // If a delayed-release was scheduled from a previous tap, cancel
      // it — we're starting a new press cycle.
      if (releaseTimer.current !== null) {
        clearTimeout(releaseTimer.current);
        releaseTimer.current = null;
      }
      emu.pressButton(button);
      pressedAt.current = performance.now();
    },
    [emu, button],
  );
  const release = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      e.preventDefault();
      const held = performance.now() - pressedAt.current;
      const remaining = MIN_HOLD_MS - held;
      if (remaining <= 0) {
        emu.releaseButton(button);
      } else {
        // User released too fast; defer release so the GB still sees
        // ~5 frames of "down" state before "up".
        releaseTimer.current = setTimeout(() => {
          emu.releaseButton(button);
          releaseTimer.current = null;
        }, remaining);
      }
    },
    [emu, button],
  );
  return (
    <button
      style={{ ...BTN_STYLE, ...style }}
      onPointerDown={press}
      onPointerUp={release}
      onPointerCancel={release}
    >
      {label}
    </button>
  );
}

export function Gamepad({ emu }: { emu: WasmBoyEmulator }) {
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
        <PadButton label="↑" emu={emu} button="UP" />
        <span />
        <PadButton label="←" emu={emu} button="LEFT" />
        <span />
        <PadButton label="→" emu={emu} button="RIGHT" />
        <span />
        <PadButton label="↓" emu={emu} button="DOWN" />
        <span />
      </div>

      {/* A/B + Start/Select */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          <PadButton label="B" emu={emu} button="B" style={{ background: '#421', color: '#fc6' }} />
          <PadButton label="A" emu={emu} button="A" style={{ background: '#421', color: '#fc6' }} />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <PadButton
            label="SELECT"
            emu={emu}
            button="SELECT"
            style={{ width: 80, fontSize: 11 }}
          />
          <PadButton
            label="START"
            emu={emu}
            button="START"
            style={{ width: 80, fontSize: 11 }}
          />
        </div>
      </div>
    </div>
  );
}
