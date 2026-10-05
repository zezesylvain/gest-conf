import { HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { provideI18nTesting } from '../../testing';
import { GcApiError } from './api-error';
import { SESSION_EXPIRED_HANDLER } from './interceptors';
import { provideGestconfApi } from './provide-api';

describe('Intercepteurs de l’API', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let expired: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    expired = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideI18nTesting(),
        provideGestconfApi(),
        provideHttpClientTesting(),
        { provide: SESSION_EXPIRED_HANDLER, useValue: expired },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  afterEach(() => backend.verify());

  it('ajoute Accept-Language sur les appels à l’API seulement', () => {
    void firstValueFrom(http.get('/api/v1/me'));
    expect(backend.expectOne('/api/v1/me').request.headers.get('Accept-Language')).toBe('fr');
    void firstValueFrom(http.get('/assets/x.json'));
    expect(backend.expectOne('/assets/x.json').request.headers.has('Accept-Language')).toBe(false);
  });

  it('401 sous /api/v1/ : session expirée signalée, erreur normalisée', async () => {
    const result = firstValueFrom(http.get('/api/v1/me')).catch((error: unknown) => error);
    backend
      .expectOne('/api/v1/me')
      .flush(
        { code: 'not_authenticated', message: 'Non.', fields: {} },
        { status: 401, statusText: '' },
      );
    const error = await result;
    expect(error).toBeInstanceOf(GcApiError);
    expect((error as GcApiError).code).toBe('not_authenticated');
    expect(expired).toHaveBeenCalledTimes(1);
  });

  it('401 sous /api/_allauth/ (flux mfa_authenticate) : aucune redirection', async () => {
    const result = firstValueFrom(http.post('/api/_allauth/browser/v1/auth/login', {})).catch(
      (error: unknown) => error,
    );
    backend
      .expectOne('/api/_allauth/browser/v1/auth/login')
      .flush(
        { status: 401, data: { flows: [{ id: 'mfa_authenticate', is_pending: true }] }, meta: {} },
        { status: 401, statusText: '' },
      );
    expect(await result).toBeInstanceOf(GcApiError);
    expect(expired).not.toHaveBeenCalled();
  });

  it('csrf_failed : recharge le cookie puis une seule nouvelle tentative', async () => {
    const result = firstValueFrom(http.patch('/api/v1/me/profile', {}));
    const csrf = { code: 'csrf_failed', message: 'CSRF', fields: {} };
    backend.expectOne('/api/v1/me/profile').flush(csrf, { status: 403, statusText: '' });
    // Aucune nouvelle tentative avant la fin de l'amorçage (cookie pas encore posé).
    expect(backend.match('/api/v1/me/profile')).toEqual([]);
    backend
      .expectOne('/api/_allauth/browser/v1/auth/session')
      .flush({ status: 401 }, { status: 401, statusText: '' });
    backend.expectOne('/api/v1/me/profile').flush({ ok: true });
    expect(await result).toEqual({ ok: true });
  });

  it('csrf_failed deux fois : pas de boucle, erreur renvoyée', async () => {
    const result = firstValueFrom(http.patch('/api/v1/me/profile', {})).catch(
      (error: unknown) => error,
    );
    const csrf = { code: 'csrf_failed', message: 'CSRF', fields: {} };
    backend.expectOne('/api/v1/me/profile').flush(csrf, { status: 403, statusText: '' });
    backend
      .expectOne('/api/_allauth/browser/v1/auth/session')
      .flush({ status: 401 }, { status: 401, statusText: '' });
    backend.expectOne('/api/v1/me/profile').flush(csrf, { status: 403, statusText: '' });
    expect(((await result) as GcApiError).code).toBe('csrf_failed');
  });
});
