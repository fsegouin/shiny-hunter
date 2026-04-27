/**
 * EventMacro replay — port of `src/shiny_hunter/macro.py` (event-log
 * format only; the YAML "step" format is Python-only for now).
 *
 * Frame-indexed press/release events; replay walks the list, ticks to
 * each frame, and applies the press/release. PyBoy and WasmBoy both
 * being deterministic, the resulting DVs depend only on the starting
 * state and any pre-macro jitter.
 */
import type { Button, WasmBoyEmulator } from './emulator/wasmboy';

const VALID_BUTTONS = new Set<Lowercase<Button>>([
  'a', 'b', 'start', 'select', 'up', 'down', 'left', 'right',
]);

export interface EventEntry {
  frame: number;
  /** Lowercase button name. */
  button: Lowercase<Button>;
  kind: 'press' | 'release';
}

export interface EventMacro {
  events: EventEntry[];
  totalFrames: number;
  romSha1?: string;
  fromState?: string;
}

interface RawEvent {
  frame: number;
  press?: string;
  release?: string;
}

interface RawMacro {
  events?: RawEvent[];
  total_frames?: number;
  rom_sha1?: string;
  from_state?: string;
}

function coerceButton(name: string): Lowercase<Button> {
  const lower = name.toLowerCase();
  if (!VALID_BUTTONS.has(lower as Lowercase<Button>)) {
    throw new Error(`unknown button "${name}"`);
  }
  return lower as Lowercase<Button>;
}

export function parseEventMacro(doc: unknown): EventMacro {
  if (typeof doc !== 'object' || doc === null) {
    throw new Error('macro JSON must be an object');
  }
  const raw = doc as RawMacro;
  const rawEvents = raw.events ?? [];
  if (!Array.isArray(rawEvents)) {
    throw new Error("macro 'events' must be an array");
  }
  const events: EventEntry[] = rawEvents.map((e, i): EventEntry => {
    if (typeof e.frame !== 'number' || e.frame < 0) {
      throw new Error(`event[${i}] missing/negative 'frame'`);
    }
    if (e.press !== undefined && e.release !== undefined) {
      throw new Error(`event[${i}] has both 'press' and 'release'`);
    }
    if (e.press !== undefined) {
      return { frame: e.frame, button: coerceButton(e.press), kind: 'press' };
    }
    if (e.release !== undefined) {
      return { frame: e.frame, button: coerceButton(e.release), kind: 'release' };
    }
    throw new Error(`event[${i}] must have 'press' or 'release'`);
  });
  for (let i = 1; i < events.length; i++) {
    if (events[i].frame < events[i - 1].frame) {
      throw new Error(`event frames must be non-decreasing (event[${i}])`);
    }
  }
  const last = events.length ? events[events.length - 1].frame : 0;
  const totalFrames = raw.total_frames ?? last;
  if (totalFrames < last) {
    throw new Error("'total_frames' is before the last event frame");
  }
  return {
    events,
    totalFrames,
    romSha1: raw.rom_sha1,
    fromState: raw.from_state,
  };
}

const BUTTON_LOWER_TO_UPPER: Record<Lowercase<Button>, Button> = {
  a: 'A', b: 'B', start: 'START', select: 'SELECT',
  up: 'UP', down: 'DOWN', left: 'LEFT', right: 'RIGHT',
};

/**
 * Replay a macro against an already-positioned emulator. Caller is
 * responsible for loadState + any pre-macro jitter (`tick(delay)`).
 */
export async function replayMacro(emu: WasmBoyEmulator, macro: EventMacro): Promise<void> {
  let cur = 0;
  for (const ev of macro.events) {
    if (ev.frame > cur) {
      await emu.tick(ev.frame - cur);
      cur = ev.frame;
    }
    const button = BUTTON_LOWER_TO_UPPER[ev.button];
    if (ev.kind === 'press') {
      emu.pressButton(button);
    } else {
      emu.releaseButton(button);
    }
  }
  if (macro.totalFrames > cur) {
    await emu.tick(macro.totalFrames - cur);
  }
  // Leave joypad clean so the next attempt starts from a known state.
  emu.clearJoypad();
}
