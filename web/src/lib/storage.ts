import type { WasmBoySaveState } from './state';
import { cloneState } from './state';
import type { EventMacro } from './macro';
import type { GameName, Region } from './games';

const DB_NAME = 'shiny-hunter';
const DB_VERSION = 1;
const STORE_NAME = 'checkpoints';

export interface Checkpoint {
  /** `${game}/${region}` */
  id: string;
  game: GameName;
  region: Region;
  savedState: WasmBoySaveState;
  macro: EventMacro | null;
  verifiedSpecies: string;
  date: number;
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function saveCheckpoint(cp: Checkpoint): Promise<void> {
  const db = await open();
  const stored: Checkpoint = {
    ...cp,
    savedState: cloneState(cp.savedState),
    macro: cp.macro ? { ...cp.macro } : null,
  };
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).put(stored);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function loadCheckpoint(game: GameName, region: Region): Promise<Checkpoint | null> {
  const db = await open();
  const id = `${game}/${region}`;
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).get(id);
    req.onsuccess = () => {
      const cp = req.result as Checkpoint | undefined;
      if (cp) {
        cp.savedState = cloneState(cp.savedState);
      }
      resolve(cp ?? null);
    };
    req.onerror = () => reject(req.error);
  });
}

export async function listCheckpoints(): Promise<Checkpoint[]> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const req = tx.objectStore(STORE_NAME).getAll();
    req.onsuccess = () => resolve(req.result as Checkpoint[]);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteCheckpoint(game: GameName, region: Region): Promise<void> {
  const db = await open();
  const id = `${game}/${region}`;
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    tx.objectStore(STORE_NAME).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
