'use client';

interface ShinyResultProps {
  speciesName: string;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  attempt: number;
  delay: number;
  onPlay: () => void;
  onDownloadSav: () => void;
  onKeepScanning: () => void;
}

export default function ShinyResult({
  speciesName,
  dvs,
  attempt,
  delay,
  onPlay,
  onDownloadSav,
  onKeepScanning,
}: ShinyResultProps) {
  return (
    <div className="shiny-result">
      <h2 className="shiny-header">SHINY FOUND!</h2>
      <p className="shiny-species">{speciesName}</p>
      <div className="stats-bar">
        <span>ATK {dvs.atk}</span>
        <span>DEF {dvs.def}</span>
        <span>SPD {dvs.spd}</span>
        <span>SPC {dvs.spc}</span>
        <span>HP {dvs.hp}</span>
      </div>
      <p className="muted">
        Attempt #{attempt} &middot; Delay {delay}
      </p>
      <div className="row">
        <button onClick={onPlay}>Play</button>
        <button onClick={onDownloadSav}>Download .sav</button>
        <button onClick={onKeepScanning}>Keep Scanning</button>
      </div>
    </div>
  );
}
