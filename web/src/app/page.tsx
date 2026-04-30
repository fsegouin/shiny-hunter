'use client';

import { useCallback, useState } from 'react';
import type { GameConfig } from '@/lib/games';
import type { WasmBoySaveState } from '@/lib/state';
import type { EventMacro } from '@/lib/macro';
import StepIndicator from './components/StepIndicator';
import SaveState from './steps/SaveState';
import RecordMacro from './steps/RecordMacro';
import Hunt from './steps/Hunt';

interface WizardData {
  romBytes: Uint8Array | null;
  config: GameConfig | null;
  savedState: WasmBoySaveState | null;
  macro: EventMacro | null;
  verifiedSpecies: string;
}

export default function HuntPage() {
  const [step, setStep] = useState(0);
  const [data, setData] = useState<WizardData>({
    romBytes: null,
    config: null,
    savedState: null,
    macro: null,
    verifiedSpecies: '',
  });

  const stepDefs = [
    {
      label: 'Save State',
      summary: data.config ? `${data.config.game}/${data.config.region}` : undefined,
    },
    {
      label: 'Record Macro',
      summary: data.macro
        ? `${data.macro.events.length} events — ${data.verifiedSpecies}`
        : undefined,
    },
    {
      label: 'Hunt',
    },
  ];

  const onStep1Complete = useCallback((result: {
    romBytes: Uint8Array;
    config: GameConfig;
    savedState: WasmBoySaveState;
  }) => {
    setData(d => ({
      ...d,
      romBytes: result.romBytes,
      config: result.config,
      savedState: result.savedState,
    }));
    setStep(1);
  }, []);

  const onStep2Complete = useCallback((macro: EventMacro, verifiedSpecies: string) => {
    setData(d => ({ ...d, macro, verifiedSpecies }));
    setStep(2);
  }, []);

  return (
    <main>
      <h1>shiny-hunter web</h1>
      <StepIndicator steps={stepDefs} currentStep={step} />

      {step === 0 && (
        <SaveState onComplete={onStep1Complete} />
      )}

      {step === 1 && data.romBytes && data.config && data.savedState && (
        <RecordMacro
          romBytes={data.romBytes}
          config={data.config}
          savedState={data.savedState}
          onComplete={onStep2Complete}
        />
      )}

      {step === 2 && data.romBytes && data.config && data.savedState && data.macro && (
        <Hunt
          romBytes={data.romBytes}
          config={data.config}
          savedState={data.savedState}
          macro={data.macro}
        />
      )}
    </main>
  );
}
