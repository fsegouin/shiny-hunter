'use client';

import { useState } from 'react';

export interface AttemptResult {
  attempt: number;
  delay: number;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  shiny: boolean;
}

interface MonitorGridProps {
  attempts: AttemptResult[];
}

export default function MonitorGrid({ attempts }: MonitorGridProps) {
  const [hovered, setHovered] = useState<number | null>(null);

  return (
    <div className="monitor-grid-wrap">
      <div className="monitor-grid">
        {attempts.map((a, i) => (
          <div
            key={i}
            className={`grid-dot${a.shiny ? ' grid-dot-shiny' : ''}`}
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            {hovered === i && (
              <div className="grid-tooltip">
                #{a.attempt} delay {a.delay}
                <br />
                ATK {a.dvs.atk} DEF {a.dvs.def} SPD {a.dvs.spd} SPC{' '}
                {a.dvs.spc} HP {a.dvs.hp}
                {a.shiny && <br />}
                {a.shiny && <strong className="ok">SHINY</strong>}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
