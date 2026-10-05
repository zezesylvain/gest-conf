import { HttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { provideI18nTesting } from '../../testing';
import { GcApiError } from './api-error';
import { ReauthenticationPrompt } from '../auth/reauthentication';
import { MFA_CHALLENGE_HANDLER, SESSION_EXPIRED_HANDLER } from './interceptors';
import { provideGestconfApi } from './provide-api';

describe('Intercepteurs de l’API', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let expired: ReturnType<typeof vi.fn>;
  let mfaChallenge: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    expired = vi.fn();
    mfaChallenge = vi.fn();
    TestBed.configureTestingModule({
      providers: [
        provideI18nTesting(),
        provideGestconfApi(),
        provideHttpClientTesting(),
        { provide: SESSION_EXPIRED_HANDLER, useValue: expired },
        { provide: MFA_CHALLENGE_HANDLER, useValue: mfaChallenge },
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

  it('reauthentication_required : fenêtre, puis une seule nouvelle tentative', async () => {
    const prompt = vi.fn().mockResolvedValue(true);
    TestBed.inject(ReauthenticationPrompt).register(prompt);
    const result = firstValueFrom(http.post('/api/v1/manage/editions/1/status', {}));
    const refusal = { code: 'reauthentication_required', message: 'Non.', fields: {} };
    backend
      .expectOne('/api/v1/manage/editions/1/status')
      .flush(refusal, { status: 403, statusText: '' });
    const retry = await vi.waitFor(() => backend.expectOne('/api/v1/manage/editions/1/status'));
    retry.flush({ ok: true });
    expect(await result).toEqual({ ok: true });
    expect(prompt).toHaveBeenCalledTimes(1);
  });

  it('reauthentication_required sans fenêtre : l’erreur remonte', async () => {
    const result = firstValueFrom(http.post('/api/v1/x', {})).catch((error: unknown) => error);
    backend
      .expectOne('/api/v1/x')
      .flush(
        { code: 'reauthentication_required', message: 'Non.', fields: {} },
        { status: 403, statusText: '' },
      );
    expect(((await result) as GcApiError).code).toBe('reauthentication_required');
  });

  it('mfa_required : traitement 2FA appelé, erreur transmise', async () => {
    const result = firstValueFrom(http.get('/api/v1/manage/editions/1')).catch(
      (error: unknown) => error,
    );
    backend
      .expectOne('/api/v1/manage/editions/1')
      .flush(
        { code: 'mfa_required', message: 'Non.', fields: {} },
        { status: 403, statusText: '' },
      );
    expect(((await result) as GcApiError).code).toBe('mfa_required');
    expect(mfaChallenge).toHaveBeenCalledWith('mfa_required');
  });
});
