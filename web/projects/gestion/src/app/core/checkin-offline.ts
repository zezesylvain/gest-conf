import { inject, Injectable, InjectionToken } from '@angular/core';
import type { Bundle, BundleEntry, CheckinMethod, CheckinOutcome } from '@gestconf/shared';

/**
 * Accueil hors ligne (plan L7, K5) : **liste de pointage** téléchargée et **file de
 * pointages** en attente, gardées dans IndexedDB.
 *
 * - La liste est minimale (empreinte du jeton, référence, nom, catégorie, déjà pointé) ;
 *   elle est effacée à 48 h (`expires_at` du serveur) et à la déconnexion.
 * - La file contient le **jeton lu** (seule preuve acceptée par le serveur, bilan de
 *   L7.2) jusqu'à la synchronisation ; elle est donc effacée elle aussi à la déconnexion,
 *   après avertissement s'il reste des pointages non envoyés.
 * - Aucune décision locale n'est définitive : le serveur revérifie chaque pointage à la
 *   synchronisation (règle n° 2) et renvoie l'état réel.
 */

/** Liste de pointage telle que gardée sur l'appareil. */
export type StoredBundle = Bundle;

/** Pointage en attente d'envoi (élément de `POST …/checkin/sync`). */
export interface QueuedCheckin {
  idempotency_key: string;
  edition_id: number;
  method: CheckinMethod;
  token?: string;
  reference?: string;
  /** Empreinte du jeton : badge déjà pointé sur cet appareil, sans relire le jeton. */
  token_hash?: string;
  /** `null` : accueil ; sinon session du programme publié (K7). */
  session: number | null;
  scanned_at: string;
  /** Nom affiché, pour la liste des pointages en attente. */
  name: string;
}

/** Stockage de l'appareil : IndexedDB en vrai, mémoire dans les tests. */
export interface OfflineBackend {
  getBundle(editionId: number): Promise<StoredBundle | undefined>;
  putBundle(bundle: StoredBundle): Promise<void>;
  deleteBundle(editionId: number): Promise<void>;
  queue(editionId?: number): Promise<QueuedCheckin[]>;
  enqueue(item: QueuedCheckin): Promise<void>;
  dequeue(keys: readonly string[]): Promise<void>;
  clear(): Promise<void>;
}

const DB_NAME = 'gestconf-checkin';
const BUNDLES = 'bundles';
const QUEUE = 'queue';

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function done(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

/** IndexedDB : une base, deux magasins (listes par édition, file par clé d'idempotence). */
export class IndexedDbBackend implements OfflineBackend {
  private database: Promise<IDBDatabase> | null = null;

  private open(): Promise<IDBDatabase> {
    this.database ??= new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = () => {
        const db = req.result;
        db.createObjectStore(BUNDLES, { keyPath: 'edition_id' });
        db.createObjectStore(QUEUE, { keyPath: 'idempotency_key' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return this.database;
  }

  private async store(name: string, mode: IDBTransactionMode) {
    const transaction = (await this.open()).transaction(name, mode);
    return { store: transaction.objectStore(name), done: () => done(transaction) };
  }

  async getBundle(editionId: number): Promise<StoredBundle | undefined> {
    const { store } = await this.store(BUNDLES, 'readonly');
    return request<StoredBundle | undefined>(store.get(editionId));
  }

  async putBundle(bundle: StoredBundle): Promise<void> {
    const { store, done } = await this.store(BUNDLES, 'readwrite');
    store.put(bundle);
    await done();
  }

  async deleteBundle(editionId: number): Promise<void> {
    const { store, done } = await this.store(BUNDLES, 'readwrite');
    store.delete(editionId);
    await done();
  }

  async queue(editionId?: number): Promise<QueuedCheckin[]> {
    const { store } = await this.store(QUEUE, 'readonly');
    const items = await request<QueuedCheckin[]>(store.getAll());
    return items
      .filter((item) => editionId === undefined || item.edition_id === editionId)
      .sort((a, b) => a.scanned_at.localeCompare(b.scanned_at));
  }

  async enqueue(item: QueuedCheckin): Promise<void> {
    const { store, done } = await this.store(QUEUE, 'readwrite');
    store.put(item);
    await done();
  }

  async dequeue(keys: readonly string[]): Promise<void> {
    const { store, done } = await this.store(QUEUE, 'readwrite');
    for (const key of keys) store.delete(key);
    await done();
  }

  async clear(): Promise<void> {
    const db = await this.open();
    const transaction = db.transaction([BUNDLES, QUEUE], 'readwrite');
    transaction.objectStore(BUNDLES).clear();
    transaction.objectStore(QUEUE).clear();
    await done(transaction);
  }
}

/** Mémoire : tests, et repli d'un navigateur sans IndexedDB (rien ne survit au rechargement). */
export class MemoryBackend implements OfflineBackend {
  readonly bundles = new Map<number, StoredBundle>();
  readonly items = new Map<string, QueuedCheckin>();

  async getBundle(editionId: number) {
    return this.bundles.get(editionId);
  }
  async putBundle(bundle: StoredBundle) {
    this.bundles.set(bundle.edition_id, bundle);
  }
  async deleteBundle(editionId: number) {
    this.bundles.delete(editionId);
  }
  async queue(editionId?: number) {
    return [...this.items.values()]
      .filter((item) => editionId === undefined || item.edition_id === editionId)
      .sort((a, b) => a.scanned_at.localeCompare(b.scanned_at));
  }
  async enqueue(item: QueuedCheckin) {
    this.items.set(item.idempotency_key, item);
  }
  async dequeue(keys: readonly string[]) {
    for (const key of keys) this.items.delete(key);
  }
  async clear() {
    this.bundles.clear();
    this.items.clear();
  }
}

export const OFFLINE_BACKEND = new InjectionToken<OfflineBackend>('OFFLINE_BACKEND', {
  providedIn: 'root',
  factory: () => (typeof indexedDB === 'undefined' ? new MemoryBackend() : new IndexedDbBackend()),
});

/** Empreinte SHA-256 (hexadécimal) du texte du QR encodé en UTF-8, comme le serveur. */
export async function tokenHash(token: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(token));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/** Clé d'idempotence d'un pointage (`[A-Za-z0-9_-]{8,64}` côté serveur). */
export function idempotencyKey(): string {
  return crypto.randomUUID().replaceAll('-', '');
}

/** Référence d'inscription saisie à la main (« gc27-i00042 » → « GC27-I00042 »). */
export function normalizeReference(value: string): string | null {
  const reference = value.trim().toUpperCase();
  return /^[A-Z0-9_-]+-I\d{1,10}$/.test(reference) ? reference : null;
}

/**
 * Décision locale, faute de réseau : la personne figure-t-elle dans la liste ?
 * `offline_absent` : ni dans la liste ni parmi les badges retirés (inconnu, en attente de
 * paiement, inscrit après le téléchargement…) : diriger vers le comptoir, rien n'est mis
 * en file.
 */
export type LocalOutcome =
  | Extract<CheckinOutcome, 'checked_in' | 'already_checked_in' | 'cancelled' | 'replaced'>
  | 'offline_absent';

export interface LocalDecision {
  outcome: LocalOutcome;
  entry?: BundleEntry;
  reference?: string;
}

export function decideLocally(
  bundle: StoredBundle,
  hash: string,
  locallyChecked: ReadonlySet<string>,
  session: number | null,
): LocalDecision {
  const entry = bundle.entries.find((item) => item.token_hash === hash);
  if (entry) {
    // En session, « déjà pointé » n'est connu que du serveur : il dédoublonne.
    const already = session === null && (entry.checked_in || locallyChecked.has(hash));
    return { outcome: already ? 'already_checked_in' : 'checked_in', entry };
  }
  const retired = bundle.retired.find((item) => item.token_hash === hash);
  if (retired) {
    return { outcome: retired.reason, reference: retired.reference };
  }
  return { outcome: 'offline_absent' };
}

export function isExpired(bundle: StoredBundle, now = new Date()): boolean {
  return new Date(bundle.expires_at).getTime() <= now.getTime();
}

/**
 * Accès à la liste et à la file, partagé par l'écran d'accueil et la déconnexion (coque).
 * Une liste expirée est effacée à la lecture.
 */
@Injectable({ providedIn: 'root' })
export class OfflineCheckinStore {
  private readonly backend = inject(OFFLINE_BACKEND);

  async bundle(editionId: number, now = new Date()): Promise<StoredBundle | undefined> {
    const bundle = await this.backend.getBundle(editionId);
    if (bundle && isExpired(bundle, now)) {
      await this.backend.deleteBundle(editionId);
      return undefined;
    }
    return bundle;
  }

  saveBundle(bundle: StoredBundle): Promise<void> {
    return this.backend.putBundle(bundle);
  }

  deleteBundle(editionId: number): Promise<void> {
    return this.backend.deleteBundle(editionId);
  }

  queue(editionId?: number): Promise<QueuedCheckin[]> {
    return this.backend.queue(editionId);
  }

  enqueue(item: QueuedCheckin): Promise<void> {
    return this.backend.enqueue(item);
  }

  dequeue(keys: readonly string[]): Promise<void> {
    return this.backend.dequeue(keys);
  }

  /** Nombre de pointages non envoyés, toutes éditions (avertissement à la déconnexion). */
  async pending(): Promise<number> {
    try {
      return (await this.backend.queue()).length;
    } catch {
      return 0;
    }
  }

  /** Déconnexion : liste et file effacées (K5 ; le jeton est un titre d'accès). */
  async clear(): Promise<void> {
    try {
      await this.backend.clear();
    } catch {
      // Base absente ou inaccessible : rien à effacer.
    }
  }
}
