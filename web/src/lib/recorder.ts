/**
 * In-browser macro recorder for the web shiny hunter.
 *
 * Takes over WasmBoy's frame loop: pauses WasmBoy's internal RAF
 * playback, runs its own requestAnimationFrame loop, polls the
 * responsive-gamepad each frame for button transitions, and returns
 * an EventMacro when stopped.
 */
import type { Button, WasmBoyEmulator } from './emulator/wasmboy';
import type { EventEntry, EventMacro } from './macro';

/** Maps responsive-gamepad state keys to our Button type. */
const GAMEPAD_KEY_TO_BUTTON: Record<string, Button> = {
  DPAD_UP: 'UP',
  DPAD_DOWN: 'DOWN',
  DPAD_LEFT: 'LEFT',
  DPAD_RIGHT: 'RIGHT',
  A: 'A',
  B: 'B',
  START: 'START',
  SELECT: 'SELECT',
};

const ALL_GAMEPAD_KEYS = Object.keys(GAMEPAD_KEY_TO_BUTTON);

export interface RecordingSession {
  /** Ends the recording, releases held buttons, and returns the macro. */
  stop(): EventMacro;
}

/**
 * Start recording a macro. Pauses WasmBoy's internal playback and
 * drives its own requestAnimationFrame loop at ~60fps.
 *
 * Returns immediately with a `RecordingSession` handle; call
 * `session.stop()` to end recording and retrieve the EventMacro.
 */
export function startRecording(emu: WasmBoyEmulator): RecordingSession {
  const events: EventEntry[] = [];
  let frame = 0;
  let running = true;

  // Track which buttons are currently held so we can detect transitions.
  const held: Record<string, boolean> = {};
  for (const key of ALL_GAMEPAD_KEYS) {
    held[key] = false;
  }

  // Pause WasmBoy's own RAF loop so we can drive frames manually.
  // emu.pause() is async but we fire-and-forget here — the first
  // requestAnimationFrame tick won't fire until the microtask queue
  // drains, so pause completes before we start ticking.
  void emu.pause();

  const loop = async () => {
    if (!running) return;

    frame++;

    // Poll responsive-gamepad for current button states.
    const state = emu.responsiveGamepad.getState() as Record<string, boolean>;

    for (const key of ALL_GAMEPAD_KEYS) {
      const pressed = !!state[key];
      const wasHeld = held[key];

      if (pressed !== wasHeld) {
        held[key] = pressed;
        const button = GAMEPAD_KEY_TO_BUTTON[key];
        events.push({
          frame,
          button: button.toLowerCase() as Lowercase<Button>,
          kind: pressed ? 'press' : 'release',
        });

        if (pressed) {
          emu.pressButton(button);
        } else {
          emu.releaseButton(button);
        }
      }
    }

    // Advance one emulator frame (renders to canvas).
    await emu.tick(1);

    // Schedule next frame.
    if (running) {
      requestAnimationFrame(() => void loop());
    }
  };

  // Kick off the recording loop.
  requestAnimationFrame(() => void loop());

  return {
    stop(): EventMacro {
      running = false;

      // Release any buttons still held and record the release events.
      for (const key of ALL_GAMEPAD_KEYS) {
        if (held[key]) {
          held[key] = false;
          const button = GAMEPAD_KEY_TO_BUTTON[key];
          events.push({
            frame,
            button: button.toLowerCase() as Lowercase<Button>,
            kind: 'release',
          });
        }
      }

      emu.clearJoypad();

      return {
        events,
        totalFrames: frame,
      };
    },
  };
}
