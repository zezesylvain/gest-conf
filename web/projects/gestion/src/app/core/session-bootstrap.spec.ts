import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { AuthApi, GcApiError, MeStore, SessionStore } from '@gestconf/shared';

import { Connectivity, isUnreachable } from './reception';
import { SessionBootstrap } from './session-bootstrap';

function setup(error: unknown) {
  const assign = vi.fn();
  TestBed.configureTestingModule({
    providers: [
      { provide: AuthApi, useValue: { loadSession: vi.fn().mockRejectedValue(error) } },
      { provide: SessionStore, useValue: { clear: vi.fn(), authenticated: () => false } },
      { provide: MeStore, useValue: { load: vi.fn() } },
      {
        provide: DOCUMENT,
        useValue: {
          defaultView: {
            location: { assign, pathname: '/gestion/editions/3/accueil', search: '' },
          },
        },
      },
    ],
  });
  return { assign };
}

describe('Démarrage de la gestion sans réseau (plan L7, K5)', () => {
  it('serveur injoignable : statut 0, ou 502 à 504 (le service worker répond 504)', () => {
    expect(isUnreachable(new GcApiError(0, 'network_error', ''))).toBe(true);
    expect(isUnreachable(new GcApiError(504, 'server_error', ''))).toBe(true);
    expect(isUnreachable(new GcApiError(500, 'server_error', ''))).toBe(false);
    expect(isUnreachable(new GcApiError(403, 'permission_denied', ''))).toBe(false);
    expect(isUnreachable(new Error('x'))).toBe(false);
  });

  it('session illisible faute de réseau : pas de renvoi vers la connexion, mode hors ligne', async () => {
    const { assign } = setup(new GcApiError(504, 'server_error', ''));
    await TestBed.inject(SessionBootstrap).start();
    expect(assign).not.toHaveBeenCalled();
    expect(TestBed.inject(Connectivity).startedOffline()).toBe(true);
  });

  it('autre échec : session vidée, connexion du portail', async () => {
    const { assign } = setup(new GcApiError(500, 'server_error', ''));
    await TestBed.inject(SessionBootstrap).start();
    expect(assign).toHaveBeenCalledWith(expect.stringContaining('/compte/connexion'));
    expect(TestBed.inject(Connectivity).startedOffline()).toBe(false);
  });
});
