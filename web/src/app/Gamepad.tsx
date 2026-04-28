'use client';

import { useEffect, useRef } from 'react';
import type { WasmBoyEmulator } from '@/lib/emulator/wasmboy';
import './gamepad.css';

/**
 * On-screen Game Boy gamepad — fixed-position overlay matching the
 * wasmboy.app layout: d-pad bottom-left, A/B bottom-right, Start/Select
 * bottom-center. Buttons are wired through WasmBoy's bundled
 * ResponsiveGamepad instance (the standalone `responsive-gamepad`
 * package is a separate singleton WasmBoy never reads).
 *
 * The d-pad is a SINGLE element — `addDpadInput` does internal
 * hit-testing of the four quadrants, so diagonals work and small
 * finger drift doesn't release the press the way 4-button approach
 * would.
 *
 * The parent must init the emulator in 'windowed' mode (which calls
 * `enableDefaultJoypad()`) before mounting this component.
 */

export function Gamepad({ emu }: { emu: WasmBoyEmulator }) {
  const dpadRef = useRef<HTMLDivElement | null>(null);
  const aRef = useRef<HTMLButtonElement | null>(null);
  const bRef = useRef<HTMLButtonElement | null>(null);
  const startRef = useRef<HTMLButtonElement | null>(null);
  const selectRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const RG = emu.responsiveGamepad;
    const inputs = RG.RESPONSIVE_GAMEPAD_INPUTS;
    const cancels: Array<() => void> = [];

    if (dpadRef.current) {
      cancels.push(
        RG.TouchInput.addDpadInput(dpadRef.current, { allowMultipleDirections: false }),
      );
    }
    if (aRef.current) {
      cancels.push(RG.TouchInput.addButtonInput(aRef.current, inputs.A));
    }
    if (bRef.current) {
      cancels.push(RG.TouchInput.addButtonInput(bRef.current, inputs.B));
    }
    if (startRef.current) {
      cancels.push(RG.TouchInput.addButtonInput(startRef.current, inputs.START));
    }
    if (selectRef.current) {
      cancels.push(RG.TouchInput.addButtonInput(selectRef.current, inputs.SELECT));
    }
    return () => {
      for (const c of cancels) c();
    };
  }, [emu]);

  return (
    <div className="gp-overlay">
      <div ref={dpadRef} className="gp-dpad" aria-label="D-pad" />
      <button ref={bRef} className="gp-btn gp-btn-b" aria-label="B">B</button>
      <button ref={aRef} className="gp-btn gp-btn-a" aria-label="A">A</button>
      <button ref={selectRef} className="gp-btn gp-btn-select" aria-label="Select">SELECT</button>
      <button ref={startRef} className="gp-btn gp-btn-start" aria-label="Start">START</button>
    </div>
  );
}
