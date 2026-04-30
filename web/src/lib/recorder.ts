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
  /** Ends the recording, waits for any in-flight frame to finish, and returns the macro. */
  stop(): Promise<EventMacro>;
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
  let inFlightFrame: Promise<void> | null = null;

  const held: Record<string, boolean> = {};
  for (const key of ALL_GAMEPAD_KEYS) {
    held[key] = false;
  }

  void emu.pause();

  const loop = async () => {
    if (!running) return;

    frame++;

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

    await emu.tick(1);
    await emu.renderFrame();

    if (running) {
      requestAnimationFrame(() => {
        inFlightFrame = loop();
      });
    }
  };

  requestAnimationFrame(() => {
    inFlightFrame = loop();
  });

  return {
    async stop(): Promise<EventMacro> {
      running = false;

      if (inFlightFrame) {
        await inFlightFrame;
      }

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
