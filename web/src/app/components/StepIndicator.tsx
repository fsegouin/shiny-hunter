'use client';

interface StepDef {
  label: string;
  summary?: string;
}

interface StepIndicatorProps {
  steps: StepDef[];
  currentStep: number;
}

export default function StepIndicator({ steps, currentStep }: StepIndicatorProps) {
  return (
    <div className="step-indicator">
      {steps.map((step, i) => {
        const done = i < currentStep;
        const active = i === currentStep;
        const cls = done ? 'step-done' : active ? 'step-active' : 'step-pending';
        return (
          <div key={i} className={`step-item ${cls}`}>
            <span className="step-number">{i + 1}</span>
            <span className="step-label">{step.label}</span>
            {done && step.summary && (
              <span className="step-summary">{step.summary}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
