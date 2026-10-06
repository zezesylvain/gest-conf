import { inject, Injectable, signal } from '@angular/core';
import { CheckinOutcome, CheckinResult, SyncItemRequest } from '@gestconf/shared';

import {
  decideLocally,
  idempotencyKey,
  normalizeReference,
  OfflineCheckinStore,
  QueuedCheckin,
  StoredBundle,
  tokenHash,
} from './checkin-offline';
import { EventsApi } from './events-api';
import { isUnreachable } from './reception';

/** Pointages envoyés par lot (`SYNC_MAX_ITEMS` du serveur). */
export const SYNC_BATCH = 200;

/** Longueur maximale du texte d'un QR accepté par le serveur (jeton de 32 caractères). */
export const TOKEN_MAX_LENGTH = 128;

/** Résultat affiché d'un pointage, en ligne ou décidé sur l'appareil. */
export interface DeskResult {
  outcome: CheckinOutcome | 'offline_absent' | 'no_bundle' | 'bad_reference';
  /** Décidé sans réseau, à confirmer à la synchronisation. */
  offline: boolean;
  name?: string;
  reference?: string;
  /** Catégorie : code et libellés (le libellé suit la langue de l'interface). */
  category?: { code: string; label_fr: string; label_en: string };
}

/** Pointage refusé par le serveur à la synchronisation (inscription annulée entre-temps…). */
export interface RejectedCheckin {
  name: string;
  reference?: string;
  outcome: CheckinOutcome;
  scanned_at: string;
}

/** Personne admise : pointée maintenant ou déjà pointée. */
export const ADMITTED: readonly string[] = ['checked_in', 'already_checked_in'];

/**
 * Poste d'accueil (plan L7, K4 à K7) : **en ligne d'abord**, le serveur répond pour chaque
 * badge ; faute de réseau, décision sur la liste de l'appareil et mise en file, puis
 * synchronisation au retour du réseau (ou par le bouton). Le serveur revérifie tout.
 * Une instance par écran (fournie par la page).
 */
@Injectable()
export class CheckinDesk {
  private readonly api = inject(EventsApi);
  private readonly store = inject(OfflineCheckinStore);

  private editionId = 0;
  /** Empreintes admises à l'accueil depuis l'ouverture de l'écran (« déjà pointé » local). */
  private readonly admitted = new Set<string>();

  readonly bundle = signal<StoredBundle | undefined>(undefined);
  readonly queue = signal<QueuedCheckin[]>([]);
  readonly rejected = signal<RejectedCheckin[]>([]);
  readonly syncing = signal(false);
  /** Session du programme publié pointée à l'entrée ; `null` : accueil (K7). */
  readonly session = signal<number | null>(null);

  async init(editionId: number): Promise<void> {
    this.editionId = editionId;
    this.bundle.set(await this.store.bundle(editionId));
    await this.refreshQueue();
  }

  /** Télécharge la liste de pointage (journalisé par le serveur) et la garde sur l'appareil. */
  async download(): Promise<StoredBundle> {
    const bundle = await this.api.bundle(this.editionId);
    await this.store.saveBundle(bundle);
    this.bundle.set(bundle);
    return bundle;
  }

  async forget(): Promise<void> {
    await this.store.deleteBundle(this.editionId);
    this.bundle.set(undefined);
  }

  /** Badge lu par la caméra (le texte du QR est le jeton, K2). */
  async read(token: string, device: string): Promise<DeskResult> {
    if (!token || token.length > TOKEN_MAX_LENGTH) {
      // QR étranger (adresse, carte de visite…) : ce n'est pas un badge de la plateforme.
      return { outcome: 'unknown', offline: false };
    }
    const hash = await tokenHash(token);
    const key = idempotencyKey();
    const session = this.session();
    try {
      const result =
        session === null
          ? await this.api.scan(this.editionId, { token, device, idempotency_key: key })
          : await this.api.sessionScan(this.editionId, session, {
              token,
              device,
              idempotency_key: key,
            });
      if (session === null && ADMITTED.includes(result.outcome)) {
        this.admitted.add(hash);
      }
      return this.online(result);
    } catch (error) {
      if (!isUnreachable(error)) {
        throw error;
      }
    }
    return this.offlineRead(token, hash, key);
  }

  /** Référence saisie à la main (`checkin.manage`, revérifié par le serveur). */
  async enter(value: string, device: string): Promise<DeskResult> {
    const reference = normalizeReference(value);
    if (reference === null) {
      return { outcome: 'bad_reference', offline: false };
    }
    const key = idempotencyKey();
    try {
      const result = await this.api.manual(this.editionId, {
        reference,
        device,
        idempotency_key: key,
      });
      return this.online(result);
    } catch (error) {
      if (!isUnreachable(error)) {
        throw error;
      }
    }
    const bundle = this.bundle();
    if (!bundle) {
      return { outcome: 'no_bundle', offline: true, reference };
    }
    const entry = bundle.entries.find((item) => item.reference === reference);
    if (!entry) {
      const retired = bundle.retired.find((item) => item.reference === reference);
      return {
        outcome: retired?.reason ?? 'offline_absent',
        offline: true,
        reference,
      };
    }
    return this.offlineAdmit(entry.token_hash, key, { method: 'manual', reference });
  }

  /**
   * Envoie la file par lots ; chaque réponse est définitive (le serveur a tranché), elle
   * sort de la file. Les refus sont gardés pour l'affichage. Sans réseau : rien ne bouge.
   */
  async synchronize(device: string): Promise<{ sent: number; rejected: number }> {
    if (this.syncing()) {
      return { sent: 0, rejected: 0 };
    }
    this.syncing.set(true);
    let sent = 0;
    let rejectedCount = 0;
    try {
      for (;;) {
        const batch = (await this.store.queue(this.editionId)).slice(0, SYNC_BATCH);
        if (!batch.length) {
          break;
        }
        const items: SyncItemRequest[] = batch.map((item) => ({
          idempotency_key: item.idempotency_key,
          method: item.method,
          token: item.token ?? '',
          reference: item.reference ?? '',
          scanned_at: item.scanned_at,
          session: item.session,
        }));
        const response = await this.api.sync(this.editionId, device, items);
        const byKey = new Map(batch.map((item) => [item.idempotency_key, item]));
        const rejected: RejectedCheckin[] = [];
        for (const result of response.results) {
          const item = byKey.get(result.idempotency_key);
          if (item && !ADMITTED.includes(result.outcome)) {
            rejected.push({
              name: result.registration?.name ?? item.name,
              reference: result.registration?.reference ?? item.reference,
              outcome: result.outcome,
              scanned_at: item.scanned_at,
            });
          }
        }
        const answered = response.results.map((result) => result.idempotency_key);
        await this.store.dequeue(answered);
        sent += answered.length;
        rejectedCount += rejected.length;
        this.rejected.update((current) => [...rejected, ...current]);
        if (!answered.length) {
          break; // Réponse vide : ne pas boucler.
        }
      }
    } finally {
      await this.refreshQueue();
      this.syncing.set(false);
    }
    return { sent, rejected: rejectedCount };
  }

  clearRejected(): void {
    this.rejected.set([]);
  }

  private online(result: CheckinResult): DeskResult {
    const person = result.registration;
    return {
      outcome: result.outcome,
      offline: false,
      name: person?.name,
      reference: person?.reference,
      category: person
        ? {
            code: person.category,
            label_fr: person.category_label_fr,
            label_en: person.category_label_en,
          }
        : undefined,
    };
  }

  private async offlineRead(token: string, hash: string, key: string): Promise<DeskResult> {
    const bundle = this.bundle();
    if (!bundle) {
      return { outcome: 'no_bundle', offline: true };
    }
    const decision = decideLocally(bundle, hash, this.locallyChecked(), this.session());
    if (decision.outcome !== 'checked_in') {
      return {
        outcome: decision.outcome,
        offline: true,
        name: decision.entry?.name,
        reference: decision.entry?.reference ?? decision.reference,
        category: decision.entry ? this.category(decision.entry.category) : undefined,
      };
    }
    return this.offlineAdmit(hash, key, { method: 'scan', token });
  }

  private async offlineAdmit(
    hash: string,
    key: string,
    proof: { method: 'scan'; token: string } | { method: 'manual'; reference: string },
  ): Promise<DeskResult> {
    const bundle = this.bundle()!;
    const entry = bundle.entries.find((item) => item.token_hash === hash)!;
    const session = this.session();
    if (session === null && (entry.checked_in || this.locallyChecked().has(hash))) {
      return {
        outcome: 'already_checked_in',
        offline: true,
        name: entry.name,
        reference: entry.reference,
        category: this.category(entry.category),
      };
    }
    await this.store.enqueue({
      idempotency_key: key,
      edition_id: this.editionId,
      ...proof,
      token_hash: hash,
      session,
      scanned_at: new Date().toISOString(),
      name: entry.name,
    });
    if (session === null) {
      this.admitted.add(hash);
    }
    await this.refreshQueue();
    return {
      outcome: 'checked_in',
      offline: true,
      name: entry.name,
      reference: entry.reference,
      category: this.category(entry.category),
    };
  }

  private locallyChecked(): Set<string> {
    const hashes = new Set(this.admitted);
    for (const item of this.queue()) {
      if (item.session === null && item.token_hash) hashes.add(item.token_hash);
    }
    return hashes;
  }

  private category(code: string): DeskResult['category'] {
    const found = this.bundle()?.categories.find((item) => item.code === code);
    return found ?? { code, label_fr: code, label_en: code };
  }

  private async refreshQueue(): Promise<void> {
    this.queue.set(await this.store.queue(this.editionId));
  }
}
