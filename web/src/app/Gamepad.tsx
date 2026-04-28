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
 * IMPORTANT: WasmBoy *bundles* its own copy of responsive-gamepad at
 * build time. The singleton you'd get from
 * `import('responsive-gamepad')` is a SEPARATE instance whose state
 * WasmBoy never polls — registering buttons on that instance is a
 * silent no-op. We therefore use `emu.responsiveGamepad` (which the
 * wrapper exposes from `WasmBoy.ResponsiveGamepad`) so the buttons
 * attach to the same instance WasmBoy reads from.
 *
 * NOTE: the parent must init in 'windowed' mode (which calls
 * `enableDefaultJoypad()`) before mounting this component.
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
  emu,
  button,
  style,
}: {
  label: string;
  emu: WasmBoyEmulator;
  button: GbButton;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const RG = emu.responsiveGamepad;
    const inputKey = RG_INPUT_KEY[button];
    const inputId = RG.RESPONSIVE_GAMEPAD_INPUTS[inputKey];
    const cancel = RG.TouchInput.addButtonInput(ref.current, inputId);
    return cancel;
  }, [emu, button]);
  return (
    <button ref={ref} style={{ ...BTN_STYLE, ...style }}>
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
          <PadButton label="SELECT" emu={emu} button="SELECT" style={{ width: 80, fontSize: 11 }} />
          <PadButton label="START" emu={emu} button="START" style={{ width: 80, fontSize: 11 }} />
        </div>
      </div>
    </div>
  );
}
