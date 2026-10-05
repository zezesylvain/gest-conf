import { HttpErrorResponse } from '@angular/common/http';

import { GcApiError, NON_FIELD_ERRORS, toApiError } from './api-error';

function httpError(status: number, error: unknown): HttpErrorResponse {
  return new HttpErrorResponse({ status, error, url: '/api/v1/me' });
}

describe('toApiError', () => {
  it('normalise le format DRF {code, message, fields}', () => {
    const error = toApiError(
      httpError(400, {
        code: 'validation_error',
        message: 'Données invalides.',
        fields: { country: ['Code pays inconnu.'], orcid: 'Invalide' },
      }),
    );
    expect(error).toBeInstanceOf(GcApiError);
    expect(error.status).toBe(400);
    expect(error.code).toBe('validation_error');
    expect(error.message).toBe('Données invalides.');
    expect(error.fields).toEqual({ country: ['Code pays inconnu.'], orcid: ['Invalide'] });
  });

  it('normalise le format allauth {status, errors[]} (param → champ)', () => {
    const error = toApiError(
      httpError(400, {
        status: 400,
        errors: [
          { code: 'email_password_mismatch', message: 'Incorrect.', param: 'password' },
          { code: 'too_many_login_attempts', message: 'Trop.' },
        ],
      }),
    );
    expect(error.code).toBe('email_password_mismatch');
    expect(error.fields).toEqual({ password: ['Incorrect.'], [NON_FIELD_ERRORS]: ['Trop.'] });
  });

  it('garde le corps d’un 401 d’allauth (flux du protocole)', () => {
    const body = {
      status: 401,
      data: { flows: [{ id: 'login' }] },
      meta: { is_authenticated: false },
    };
    const error = toApiError(httpError(401, body));
    expect(error.code).toBe('not_authenticated');
    expect(error.body).toEqual(body);
  });

  it('donne un code générique sans corps exploitable', () => {
    expect(toApiError(httpError(0, null)).code).toBe('network_error');
    expect(toApiError(httpError(502, '<html>')).code).toBe('server_error');
    expect(toApiError(new Error('boom')).code).toBe('network_error');
  });
});
