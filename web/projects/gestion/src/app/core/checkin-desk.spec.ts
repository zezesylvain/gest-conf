import { TestBed } from '@angular/core/testing';
import { GcApiError, SyncItemRequest } from '@gestconf/shared';

import { bundle, checkinResult, PERSON } from '../pages/events/testing';
import { CheckinDesk, SYNC_BATCH } from './checkin-desk';
import { MemoryBackend, OFFLINE_BACKEND, QueuedCheckin, tokenHash } from './checkin-offline';
import { EventsApi } from './events-api';

const NETWORK = new GcApiError(0, 'network_error', '');

let api: Record<string, ReturnType<typeof vi.fn>>;
let backend: MemoryBackend;

/** Poste prêt, avec la liste de test dont les empreintes sont celles de vrais jetons. */
async function setup(withBundle = true): Promise<CheckinDesk> {
  api = {
    scan: vi.fn().mockResolvedValue(checkinResult()),
    sessionScan: vi.fn().mockResolvedValue(checkinResult()),
    manual: vi.fn().mockResolvedValue(checkinResult()),
    sync: vi.fn(),
    bundle: vi.fn(),
  };
  backend = new MemoryBackend();
  TestBed.configureTestingModule({
    providers: [
      CheckinDesk,
      { provide: EventsApi, useValue: api },
      { provide: OFFLINE_BACKEND, useValue: backend },
    ],
  });
  if (withBundle) {
    const list = bundle();
    list.entries[0].token_hash = await tokenHash('jeton-awa');
    list.entries[1].token_hash = await tokenHash('jeton-yao');
    list.retired[0].token_hash = await tokenHash('jeton-annule');
    await backend.putBundle(list);
  }
  const desk = TestBed.inject(CheckinDesk);
  await desk.init(3);
  return desk;
}

function queued(index: number): QueuedCheckin {
  return {
    idempotency_key: `k-${String(index).padStart(8, '0')}`,
    edition_id: 3,
    method: 'scan',
    token: `jeton-${index}`,
    session: null,
    scanned_at: new Date(Date.UTC(2027, 5, 1, 8, 0, index)).toISOString(),
    name: `Personne ${index}`,
  };
}

describe('CheckinDesk : poste d’accueil (plan L7, K4 à K7)', () => {
  it('en ligne : le serveur décide, rien n’est mis en file', async () => {
    const desk = await setup();
    const result = await desk.read('jeton-awa', 'entrée');
    expect(api['scan']).toHaveBeenCalledWith(3, {
      token: 'jeton-awa',
      device: 'entrée',
      idempotency_key: expect.stringMatching(/^[A-Za-z0-9_-]{8,64}$/),
    });
    expect(result).toMatchObject({ outcome: 'checked_in', offline: false, name: PERSON.name });
    expect(desk.queue()).toEqual([]);
  });

  it('sans réseau : décision sur la liste, mise en file, puis « déjà pointé » sur l’appareil', async () => {
    const desk = await setup();
    api['scan'].mockRejectedValue(NETWORK);
    const first = await desk.read('jeton-awa', 'entrée');
    expect(first).toMatchObject({ outcome: 'checked_in', offline: true, name: 'Awa Koné' });
    expect(first.category?.label_fr).toBe('Chercheur');
    expect(desk.queue()).toHaveLength(1);
    expect(desk.queue()[0]).toMatchObject({ method: 'scan', token: 'jeton-awa', session: null });
    expect((await desk.read('jeton-awa', 'entrée')).outcome).toBe('already_checked_in');
    // Déjà pointé avant le téléchargement : signalé, pas remis en file.
    expect((await desk.read('jeton-yao', 'entrée')).outcome).toBe('already_checked_in');
    expect(desk.queue()).toHaveLength(1);
  });

  it('page contrôlée par le service worker : son 504 vaut absence de réseau', async () => {
    const desk = await setup();
    api['scan'].mockRejectedValue(new GcApiError(504, 'server_error', ''));
    expect(await desk.read('jeton-awa', 'entrée')).toMatchObject({
      outcome: 'checked_in',
      offline: true,
    });
    expect(desk.queue()).toHaveLength(1);
  });

  it('sans réseau : badge retiré refusé, absent de la liste dirigé au comptoir, rien en file', async () => {
    const desk = await setup();
    api['scan'].mockRejectedValue(NETWORK);
    expect((await desk.read('jeton-annule', 'entrée')).outcome).toBe('cancelled');
    expect((await desk.read('jeton-inconnu', 'entrée')).outcome).toBe('offline_absent');
    expect(desk.queue()).toEqual([]);
  });

  it('QR étranger (texte trop long) : badge inconnu, sans appel au serveur', async () => {
    const desk = await setup();
    expect((await desk.read('x'.repeat(129), 'entrée')).outcome).toBe('unknown');
    expect(api['scan']).not.toHaveBeenCalled();
  });

  it('sans réseau ni liste : impossible de vérifier', async () => {
    const desk = await setup(false);
    api['scan'].mockRejectedValue(NETWORK);
    expect((await desk.read('jeton-awa', 'entrée')).outcome).toBe('no_bundle');
  });

  it('erreur autre que réseau (droits, 2FA) : remontée, pas de décision locale', async () => {
    const desk = await setup();
    api['scan'].mockRejectedValue(new GcApiError(403, 'permission_denied', 'Refusé'));
    await expect(desk.read('jeton-awa', 'entrée')).rejects.toBeInstanceOf(GcApiError);
    expect(desk.queue()).toEqual([]);
  });

  it('mode session (K7) : pointage de l’entrée de la session, file marquée de la session', async () => {
    const desk = await setup();
    desk.session.set(21);
    await desk.read('jeton-awa', 'salle A');
    expect(api['sessionScan']).toHaveBeenCalledWith(
      3,
      21,
      expect.objectContaining({ token: 'jeton-awa' }),
    );
    api['sessionScan'].mockRejectedValue(NETWORK);
    await desk.read('jeton-yao', 'salle A');
    expect(desk.queue()[0].session).toBe(21);
  });

  it('saisie de la référence : normalisée ; sans réseau, mise en file par référence', async () => {
    const desk = await setup();
    expect((await desk.enter('GC27 12', 'entrée')).outcome).toBe('bad_reference');
    expect(api['manual']).not.toHaveBeenCalled();
    api['manual'].mockRejectedValue(NETWORK);
    const result = await desk.enter('gc27-i00012', 'entrée');
    expect(result).toMatchObject({ outcome: 'checked_in', offline: true });
    expect(desk.queue()[0]).toMatchObject({ method: 'manual', reference: 'GC27-I00012' });
    expect(desk.queue()[0].token).toBeUndefined();
  });

  it('synchronisation : chaque réponse sort de la file, les refus sont signalés avec le nom', async () => {
    const desk = await setup();
    await backend.enqueue(queued(1));
    await backend.enqueue(queued(2));
    api['sync'].mockImplementation(
      async (_edition: number, _device: string, items: SyncItemRequest[]) => ({
        results: [
          checkinResult({ idempotency_key: items[0].idempotency_key }),
          checkinResult({
            idempotency_key: items[1].idempotency_key,
            outcome: 'cancelled',
            registration: null,
          }),
        ],
      }),
    );
    const summary = await desk.synchronize('entrée');
    expect(summary).toEqual({ sent: 2, rejected: 1 });
    expect(api['sync'].mock.calls[0][2][0]).toEqual({
      idempotency_key: 'k-00000001',
      method: 'scan',
      token: 'jeton-1',
      reference: '',
      scanned_at: queued(1).scanned_at,
      session: null,
    });
    expect(desk.queue()).toEqual([]);
    expect(desk.rejected()).toEqual([
      expect.objectContaining({ name: 'Personne 2', outcome: 'cancelled' }),
    ]);
  });

  it('synchronisation par lots de 200 ; sans réseau, la file reste intacte', async () => {
    const desk = await setup();
    for (let index = 1; index <= SYNC_BATCH + 50; index++) {
      await backend.enqueue(queued(index));
    }
    api['sync'].mockImplementation(async (_e: number, _d: string, items: SyncItemRequest[]) => ({
      results: items.map((item) => checkinResult({ idempotency_key: item.idempotency_key })),
    }));
    expect((await desk.synchronize('entrée')).sent).toBe(SYNC_BATCH + 50);
    expect(api['sync'].mock.calls.map((call) => call[2].length)).toEqual([SYNC_BATCH, 50]);

    await backend.enqueue(queued(1));
    api['sync'].mockRejectedValue(NETWORK);
    await expect(desk.synchronize('entrée')).rejects.toBe(NETWORK);
    expect(desk.queue()).toHaveLength(1);
    expect(desk.syncing()).toBe(false);
  });

  it('téléchargement : liste gardée sur l’appareil ; effacement', async () => {
    const desk = await setup(false);
    api['bundle'].mockResolvedValue(bundle());
    await desk.download();
    expect(desk.bundle()?.entries).toHaveLength(2);
    expect(await backend.getBundle(3)).toBeDefined();
    await desk.forget();
    expect(desk.bundle()).toBeUndefined();
    expect(await backend.getBundle(3)).toBeUndefined();
  });
});
