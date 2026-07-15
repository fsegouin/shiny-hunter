/**
 * Per-(game, region) configuration.
 * Mirrors `src/shiny_hunter/games/*.py`.
 *
 * Long-term we should factor this into a single JSON file at the repo
 * root that both runtimes read; for the spike, it's duplicated.
 */

export type Region = 'us' | 'jp' | 'eu' | 'de' | 'fr' | 'it' | 'es';
export type GameName =
  | 'red'
  | 'blue'
  | 'green'
  | 'yellow'
  | 'gold'
  | 'silver'
  | 'crystal';

export interface GameConfig {
  game: GameName;
  region: Region;
  /** 1 = RBGY, 2 = GSC. */
  generation: 1 | 2;
  /** Lowercase hex SHA-1 of the canonical ROM dump. */
  romSha1: string;
  /** Address of the byte holding (Atk<<4 | Def). +1 holds (Spd<<4 | Spc). */
  partyDvAddr: number;
  /** Address of wPartySpecies[0]. */
  partySpeciesAddr: number;
  /** Cartridge SRAM size in bytes (32 KiB for all but JP Crystal's MBC30). */
  sramSize: number;
  /** species id (Gen 1 internal index / Gen 2 dex number) -> lowercase name. */
  starters: Record<number, string>;
  /** post-macro frames to wait for the party to be committed. */
  postMacroSettleFrames: number;
}

const GEN2_STARTERS: Record<number, string> = {
  152: 'chikorita',
  155: 'cyndaquil',
  158: 'totodile',
};

export const GAMES: GameConfig[] = [
  {
    game: 'red',
    region: 'us',
    generation: 1,
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
    generation: 1,
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
    generation: 1,
    romSha1: 'cc7d03262ebfaf2f06772c1a480c7d9d5f4a38e1',
    partyDvAddr: 0xd185,
    partySpeciesAddr: 0xd163,
    sramSize: 0x8000,
    starters: { 0x54: 'pikachu' },
    postMacroSettleFrames: 120,
  },
  // Gen 1 JP entries omitted in the spike; add when we wire the registry
  // to the shared data file.
  //
  // Gen 2 addresses mirror src/shiny_hunter/games/*.py — see those files
  // for provenance (pret symbol files for US, opcode-literal frequency
  // analysis against retail dumps for JP).
  {
    game: 'gold',
    region: 'us',
    generation: 2,
    romSha1: 'd8b8a3600a465308c9953dfa04f0081c05bdcb94',
    partyDvAddr: 0xda3f,
    partySpeciesAddr: 0xda23,
    sramSize: 0x8000,
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
  {
    game: 'silver',
    region: 'us',
    generation: 2,
    romSha1: '49b163f7e57702bc939d642a18f591de55d92dae',
    partyDvAddr: 0xda3f,
    partySpeciesAddr: 0xda23,
    sramSize: 0x8000,
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
  {
    game: 'crystal',
    region: 'us',
    generation: 2,
    // Rev 1; Rev 0 (f4cd194bdee0d04ca4eac29e09b8e4e9d818c133) has the
    // same addresses — see findBySha1 aliasing below.
    romSha1: 'f2f52230b536214ef7c9924f483392993e226cfb',
    partyDvAddr: 0xdcf4,
    partySpeciesAddr: 0xdcd8,
    sramSize: 0x8000,
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
  {
    game: 'gold',
    region: 'jp',
    generation: 2,
    romSha1: 'a222402235d484ee8e39f3f31bae57cf13daf585', // Rev 1
    partyDvAddr: 0xda05,
    partySpeciesAddr: 0xd9e9,
    sramSize: 0x8000,
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
  {
    game: 'silver',
    region: 'jp',
    generation: 2,
    romSha1: 'a11d5ddc26eb826086593f82370b15d16404d33e', // Rev 1
    partyDvAddr: 0xda05,
    partySpeciesAddr: 0xd9e9,
    sramSize: 0x8000,
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
  {
    game: 'crystal',
    region: 'jp',
    generation: 2,
    romSha1: '95127b901bbce2407daf43cce9f45d4c27ef635d',
    partyDvAddr: 0xdcba,
    partySpeciesAddr: 0xdc9e,
    sramSize: 0x10000, // MBC30, 64 KiB (Mobile Adapter)
    starters: GEN2_STARTERS,
    postMacroSettleFrames: 120,
  },
];

/**
 * Alternate dumps that share a registered entry's RAM layout.
 *
 * A Map rather than an object literal: lookups keyed on caller-supplied
 * strings never walk the prototype chain (`__proto__`, `constructor`).
 */
const ALT_SHA1S = new Map<string, string>([
  // Crystal (US) Rev 0 -> Rev 1 entry
  [
    'f4cd194bdee0d04ca4eac29e09b8e4e9d818c133',
    'f2f52230b536214ef7c9924f483392993e226cfb',
  ],
]);

export function findBySha1(sha1: string): GameConfig | undefined {
  const needle = sha1.toLowerCase();
  const canonical = ALT_SHA1S.get(needle) ?? needle;
  return GAMES.find((g) => g.romSha1 === canonical);
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
