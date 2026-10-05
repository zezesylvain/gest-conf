import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';

import { GcApiError } from '../http/api-error';
import { AUTH_API_PREFIX } from '../http/interceptors';
import { AllauthResponse, AuthResult, toAuthResult } from './allauth';
import { SessionStore } from './session.store';

/**
 * Façade typée à la main des endpoints d'allauth headless (décision D4, plan L1 §9.2).
 *
 * Les composants ne l'appellent jamais pour autre chose que l'authentification. Un 401
 * ou un 400 d'allauth n'est pas une panne : la façade le renvoie sous forme
 * d'`AuthResult` (flux en attente, erreurs par champ). Seules les erreurs inattendues
 * (réseau, 5xx, CSRF après nouvelle tentative) sont levées en `GcApiError`.
 */
@Injectable({ providedIn: 'root' })
export class AuthApi {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionStore);

  /** Amorçage : état de la session et pose du cookie CSRF. */
  loadSession(): Promise<AuthResult> {
    return this.track(this.http.get<AllauthResponse>(this.url('auth/session')));
  }

  login(email: string, password: string): Promise<AuthResult> {
    return this.track(this.http.post<AllauthResponse>(this.url('auth/login'), { email, password }));
  }

  signup(email: string, password: string): Promise<AuthResult> {
    return this.track(
      this.http.post<AllauthResponse>(this.url('auth/signup'), { email, password }),
    );
  }

  /** Déconnexion : 401 attendu (session vidée). */
  logout(): Promise<AuthResult> {
    return this.track(this.http.delete<AllauthResponse>(this.url('auth/session')));
  }

  verifyEmail(key: string): Promise<AuthResult> {
    return this.call(this.http.post<AllauthResponse>(this.url('auth/email/verify'), { key }));
  }

  /** Demande de lien de réinitialisation : réponse identique que le compte existe ou non. */
  requestPasswordReset(email: string): Promise<AuthResult> {
    return this.call(this.http.post<AllauthResponse>(this.url('auth/password/request'), { email }));
  }

  /** Vérifie une clé de réinitialisation (en-tête, jamais dans l'URL). */
  checkPasswordResetKey(key: string): Promise<AuthResult> {
    const headers = new HttpHeaders({ 'X-Password-Reset-Key': key });
    return this.call(this.http.get<AllauthResponse>(this.url('auth/password/reset'), { headers }));
  }

  resetPassword(key: string, password: string): Promise<AuthResult> {
    return this.call(
      this.http.post<AllauthResponse>(this.url('auth/password/reset'), { key, password }),
    );
  }

  reauthenticate(password: string): Promise<AuthResult> {
    return this.track(
      this.http.post<AllauthResponse>(this.url('auth/reauthenticate'), { password }),
    );
  }

  changePassword(currentPassword: string, newPassword: string): Promise<AuthResult> {
    return this.call(
      this.http.post<AllauthResponse>(this.url('account/password/change'), {
        current_password: currentPassword,
        new_password: newPassword,
      }),
    );
  }

  private url(path: string): string {
    return `${AUTH_API_PREFIX}${path}`;
  }

  /** Appel qui reflète l'état de session renvoyé par allauth dans `SessionStore`. */
  private async track(request: Observable<AllauthResponse>): Promise<AuthResult> {
    const result = await this.call(request);
    if (result.status === 200 || result.status === 401) {
      this.session.apply(result);
    }
    return result;
  }

  private async call(request: Observable<AllauthResponse>): Promise<AuthResult> {
    try {
      const body = await firstValueFrom(request);
      return toAuthResult(body, 200);
    } catch (error) {
      if (error instanceof GcApiError && isProtocolResponse(error)) {
        return toAuthResult(error.body as AllauthResponse, error.status);
      }
      throw error;
    }
  }
}

/** Réponse d'allauth exploitable (flux, erreurs de champ) plutôt qu'une panne. */
function isProtocolResponse(error: GcApiError): boolean {
  const body = error.body as AllauthResponse | null;
  return (
    body !== null &&
    typeof body === 'object' &&
    typeof body.status === 'number' &&
    error.status >= 400 &&
    error.status < 500 &&
    error.code !== 'csrf_failed'
  );
}
