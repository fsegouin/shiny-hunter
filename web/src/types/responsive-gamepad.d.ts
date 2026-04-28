/**
 * Minimal ambient types for `responsive-gamepad@1.1.0`. The package
 * ships no .d.ts. We only declare the surface the gamepad component
 * uses; everything else stays `unknown`.
 */
declare module 'responsive-gamepad' {
  type InputKey =
    | 'DPAD_UP' | 'DPAD_RIGHT' | 'DPAD_DOWN' | 'DPAD_LEFT'
    | 'A' | 'B' | 'X' | 'Y'
    | 'START' | 'SELECT' | 'SPECIAL'
    | 'LEFT_TRIGGER' | 'RIGHT_TRIGGER'
    | 'LEFT_BUMPER' | 'RIGHT_BUMPER';

  interface TouchInputApi {
    enable(): void;
    disable(): void;
    addButtonInput(element: HTMLElement, input: string): () => void;
    addDpadInput(element: HTMLElement, options?: { allowMultipleDirections?: boolean }): () => void;
    getState(): unknown;
  }

  export const ResponsiveGamepad: {
    enable(): void;
    disable(): void;
    getState(): unknown;
    RESPONSIVE_GAMEPAD_INPUTS: Record<InputKey, string>;
    TouchInput: TouchInputApi;
  };

  export default ResponsiveGamepad;
}
