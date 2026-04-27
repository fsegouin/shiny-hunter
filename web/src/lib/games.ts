/**
 * Per-(game, region) configuration.
 * Mirrors `src/shiny_hunter/games/*.py`.
 *
 * Long-term we should factor this into a single JSON file at the repo
 * root that both runtimes read; for the spike, it's duplicated.
 */

export type Region = 'us' | 'jp' | 'eu' | 'de' | 'fr' | 'it' | 'es';
export type GameName = 'red' | 'blue' | 'green' | 'yellow';

export interface GameConfig {
  game: GameName;
  region: Region;
  /** Lowercase hex SHA-1 of the canonical ROM dump. */
  romSha1: string;
  /** Address of the byte holding (Atk<<4 | Def). +1 holds (Spd<<4 | Spc). */
  partyDvAddr: number;
  /** Address of wPartySpecies[0]. */
  partySpeciesAddr: number;
  /** Cartridge SRAM size in bytes (Red/Blue MBC3 = 32 KiB). */
  sramSize: number;
  /** species_id (Gen 1 internal hex) -> canonical lowercase name. */
  starters: Record<number, string>;
  /** post-macro frames to wait for the party to be committed. */
  postMacroSettleFrames: number;
}

export const GAMES: GameConfig[] = [
  {
    game: 'red',
    region: 'us',
    romSha1: 'ea9bcae617fdf159b045185467ae58b2e4a48b9a',
    partyDvAddr: 0xd186,
    partySpeciesAddr: 0xd164,
    sramSize: 0x8000,
    starters: { 0x99: 'bulbasaur', 0xb0: 'charmander', 0xb1: 'squirtle' },
    postMacroSettleFrames: 120,
  },
  {
    game: 'blue',
    region: 'us',
    romSha1: 'd7037c83e1ae5b39bde3c30787637ba1d4c48ce2',
    partyDvAddr: 0xd186,
    partySpeciesAddr: 0xd164,
    sramSize: 0x8000,
    starters: { 0x99: 'bulbasaur', 0xb0: 'charmander', 0xb1: 'squirtle' },
    postMacroSettleFrames: 120,
  },
  {
    game: 'yellow',
    region: 'us',
    romSha1: 'cc7d03262ebfaf2f06772c1a480c7d9d5f4a38e1',
    partyDvAddr: 0xd185,
    partySpeciesAddr: 0xd163,
    sramSize: 0x8000,
    starters: { 0x54: 'pikachu' },
    postMacroSettleFrames: 120,
  },
  // JP entries omitted in the spike; add when we wire the registry to
  // the shared data file.
];

export function findBySha1(sha1: string): GameConfig | undefined {
  const needle = sha1.toLowerCase();
  return GAMES.find((g) => g.romSha1 === needle);
}

export async function sha1OfBytes(bytes: Uint8Array): Promise<string> {
  // Browser-native; works in workers too. Re-wrap into an ArrayBuffer-backed
  // view so the types satisfy `BufferSource` regardless of the underlying
  // backing store.
  const view = new Uint8Array(bytes);
  const buf = await crypto.subtle.digest('SHA-1', view.buffer as ArrayBuffer);
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
