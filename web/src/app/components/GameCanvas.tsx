'use client';

import { forwardRef } from 'react';

interface GameCanvasProps {
  visible?: boolean;
}

const GameCanvas = forwardRef<HTMLCanvasElement, GameCanvasProps>(
  function GameCanvas({ visible = true }, ref) {
    return (
      <div
        className="canvas-wrap"
        style={{ display: visible ? 'block' : 'none' }}
      >
        <canvas ref={ref} className="emu-canvas" width={160} height={144} />
      </div>
    );
  },
);

export default GameCanvas;
