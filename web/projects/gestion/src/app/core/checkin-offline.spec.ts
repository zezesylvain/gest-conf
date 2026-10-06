import { TestBed } from '@angular/core/testing';

import { bundle } from '../pages/events/testing';
import {
  decideLocally,
  idempotencyKey,
  isExpired,
  MemoryBackend,
  normalizeReference,
  OFFLINE_BACKEND,
  OfflineCheckinStore,
  QueuedCheckin,
  tokenHash,
} from './checkin-offline';

describe('Accueil hors ligne : liste et file (plan L7, K5)', () => {
  it('empreinte SHA-256 en hexadécimal, identique à celle du serveur (hashlib)', async () => {
    // hashlib.sha256("abc".encode()).hexdigest()
    expect(await tokenHash('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    );
  });

  it('clé d’idempotence acceptée par le serveur ([A-Za-z0-9_-]{8,64}), unique', () => {
    const key = idempotencyKey();
    expect(key).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
    expect(idempotencyKey()).not.toBe(key);
  });

  it('référence saisie : normalisée, refusée si mal formée', () => {
    expect(normalizeReference(' gc27-i00042 ')).toBe('GC27-I00042');
    expect(normalizeReference('GC27-00042')).toBeNull();
    expect(normalizeReference('')).toBeNull();
  });

  it('décision locale : présent, déjà pointé (liste ou appareil), retiré, absent', () => {
    const list = bundle();
    expect(decideLocally(list, 'h-awa', new Set(), null).outcome).toBe('checked_in');
    expect(decideLocally(list, 'h-yao', new Set(), null).outcome).toBe('already_checked_in');
    expect(decideLocally(list, 'h-awa', new Set(['h-awa']), null).outcome).toBe(
      'already_checked_in',
    );
    expect(decideLocally(list, 'h-cancelled', new Set(), null)).toEqual({
      outcome: 'cancelled',
      reference: 'GC27-I00014',
    });
    expect(decideLocally(list, 'h-old', new Set(), null).outcome).toBe('replaced');
    expect(decideLocally(list, 'h-inconnu', new Set(), null).outcome).toBe('offline_absent');
  });

  it('en session, « déjà pointé » est laissé au serveur (il dédoublonne)', () => {
    expect(decideLocally(bundle(), 'h-yao', new Set(), 12).outcome).toBe('checked_in');
  });

  it('liste expirée (48 h) : effacée à la lecture', async () => {
    const backend = new MemoryBackend();
    TestBed.configureTestingModule({
      providers: [{ provide: OFFLINE_BACKEND, useValue: backend }],
    });
    const store = TestBed.inject(OfflineCheckinStore);
    const list = bundle({ expires_at: '2027-06-03T07:00:00Z' });
    await store.saveBundle(list);
    expect(await store.bundle(3, new Date('2027-06-02T07:00:00Z'))).toBeDefined();
    expect(isExpired(list, new Date('2027-06-03T07:00:00Z'))).toBe(true);
    expect(await store.bundle(3, new Date('2027-06-03T08:00:00Z'))).toBeUndefined();
    expect(backend.bundles.size).toBe(0);
  });

  it('déconnexion : liste et file effacées ; pointages en attente comptés', async () => {
    const backend = new MemoryBackend();
    TestBed.configureTestingModule({
      providers: [{ provide: OFFLINE_BACKEND, useValue: backend }],
    });
    const store = TestBed.inject(OfflineCheckinStore);
    await store.saveBundle(bundle());
    const item: QueuedCheckin = {
      idempotency_key: 'k-00000001',
      edition_id: 3,
      method: 'scan',
      token: 'jeton',
      token_hash: 'h-awa',
      session: null,
      scanned_at: '2027-06-01T08:00:00Z',
      name: 'Awa Koné',
    };
    await store.enqueue(item);
    expect(await store.pending()).toBe(1);
    await store.clear();
    expect(await store.pending()).toBe(0);
    expect(backend.bundles.size).toBe(0);
  });
});
