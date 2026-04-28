'use client';

import { useCallback } from 'react';
import type { Button as GbButton, WasmBoyEmulator } from '@/lib/emulator/wasmboy';

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
  const press = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      e.preventDefault();
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      emu.pressButton(button);
    },
    [emu, button],
  );
  const release = useCallback(
    (e: React.PointerEvent<HTMLButtonElement>) => {
      e.preventDefault();
      emu.releaseButton(button);
    },
    [emu, button],
  );
  return (
    <button
      style={{ ...BTN_STYLE, ...style }}
      onPointerDown={press}
      onPointerUp={release}
      onPointerCancel={release}
      onPointerLeave={release}
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
