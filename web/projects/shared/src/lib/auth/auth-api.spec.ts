import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { provideI18nTesting } from '../../testing';
import { GcApiError } from '../http/api-error';
import { provideGestconfApi } from '../http/provide-api';
import { AuthApi } from './auth-api';
import { SessionStore } from './session.store';

const AUTH = '/api/_allauth/browser/v1';
const USER = { id: 7, email: 'awa@univ.ci', display: 'awa@univ.ci', has_usable_password: true };

describe('AuthApi', () => {
  let api: AuthApi;
  let session: SessionStore;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideI18nTesting(),
        provideRouter([]),
        provideGestconfApi(),
        provideHttpClientTesting(),
      ],
    });
    api = TestBed.inject(AuthApi);
    session = TestBed.inject(SessionStore);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('connexion réussie : session authentifiée', async () => {
    const promise = api.login('awa@univ.ci', 'secret');
    const request = backend.expectOne(`${AUTH}/auth/login`);
    expect(request.request.body).toEqual({ email: 'awa@univ.ci', password: 'secret' });
    request.flush({ status: 200, data: { user: USER }, meta: { is_authenticated: true } });
    const result = await promise;
    expect(result.authenticated).toBe(true);
    expect(session.authenticated()).toBe(true);
    expect(session.user()?.email).toBe('awa@univ.ci');
  });

  it('401 verify_email : flux en attente, pas une erreur', async () => {
    const promise = api.signup('awa@univ.ci', 'secret-secret');
    backend.expectOne(`${AUTH}/auth/signup`).flush(
      {
        status: 401,
        data: { flows: [{ id: 'login' }, { id: 'verify_email', is_pending: true }] },
        meta: { is_authenticated: false },
      },
      { status: 401, statusText: '' },
    );
    const result = await promise;
    expect(result.pendingFlow).toBe('verify_email');
    expect(session.state()).toBe('anonymous');
  });

  it('401 reauthenticate sur une action protégée (session toujours ouverte)', async () => {
    const promise = api.changePassword('a', 'b');
    backend.expectOne(`${AUTH}/account/password/change`).flush(
      {
        status: 401,
        data: { flows: [{ id: 'reauthenticate' }] },
        meta: { is_authenticated: true },
      },
      { status: 401, statusText: '' },
    );
    expect((await promise).pendingFlow).toBe('reauthenticate');
  });

  it('400 : erreurs de champ renvoyées', async () => {
    const promise = api.login('awa@univ.ci', 'faux');
    backend.expectOne(`${AUTH}/auth/login`).flush(
      {
        status: 400,
        errors: [{ code: 'email_password_mismatch', message: 'Non.', param: 'password' }],
      },
      { status: 400, statusText: '' },
    );
    const result = await promise;
    expect(result.authenticated).toBe(false);
    expect(result.errors[0].code).toBe('email_password_mismatch');
  });

  it('clé de réinitialisation passée en en-tête, jamais dans l’URL', async () => {
    const promise = api.checkPasswordResetKey('cle-secrete');
    const request = backend.expectOne(`${AUTH}/auth/password/reset`);
    expect(request.request.headers.get('X-Password-Reset-Key')).toBe('cle-secrete');
    expect(request.request.urlWithParams).not.toContain('cle-secrete');
    request.flush({ status: 200, data: { user: USER } });
    expect((await promise).errors).toEqual([]);
  });

  it('erreur serveur : levée', async () => {
    const promise = api.loadSession();
    backend.expectOne(`${AUTH}/auth/session`).flush('<html>', { status: 500, statusText: '' });
    await expect(promise).rejects.toBeInstanceOf(GcApiError);
  });

  it('déconnexion : session vidée', async () => {
    session.apply({ status: 200, authenticated: true, user: USER, pendingFlow: null, errors: [] });
    const promise = api.logout();
    backend
      .expectOne((request) => request.method === 'DELETE' && request.url === `${AUTH}/auth/session`)
      .flush(
        { status: 401, data: { flows: [] }, meta: { is_authenticated: false } },
        { status: 401, statusText: '' },
      );
    await promise;
    expect(session.authenticated()).toBe(false);
  });
});
