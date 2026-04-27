/**
 * Determinant Values (DVs) — port of `src/shiny_hunter/dv.py`.
 *
 * Two bytes carry four 4-bit values:
 *   byte at wPartyMon1DVs:     [Atk(hi) | Def(lo)]
 *   byte at wPartyMon1DVs + 1: [Spd(hi) | Spc(lo)]
 *
 * HP DV is derived from the LSBs of the other four (not stored).
 */

export interface DVs {
  atk: number;
  def: number;
  spd: number;
  spc: number;
  hp: number;
}

export function decodeDVs(byte0: number, byte1: number): DVs {
  const atk = (byte0 >> 4) & 0xf;
  const def = byte0 & 0xf;
  const spd = (byte1 >> 4) & 0xf;
  const spc = byte1 & 0xf;
  const hp =
    ((atk & 1) << 3) | ((def & 1) << 2) | ((spd & 1) << 1) | (spc & 1);
  return { atk, def, spd, spc, hp };
}

const SHINY_ATK = new Set([2, 3, 6, 7, 10, 11, 14, 15]);

/**
 * Returns true if these DVs would yield a shiny when the Pokémon is
 * transferred to Gen 2 via the Time Capsule.
 */
export function isShiny(dvs: DVs): boolean {
  return (
    dvs.def === 10 &&
    dvs.spd === 10 &&
    dvs.spc === 10 &&
    SHINY_ATK.has(dvs.atk)
  );
}
