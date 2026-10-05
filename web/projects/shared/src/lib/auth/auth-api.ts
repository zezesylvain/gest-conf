import { HttpClient, HttpHeaders } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';

import { GcApiError } from '../http/api-error';
import { AUTH_API_PREFIX } from '../http/interceptors';
import {
  AllauthResponse,
  AuthenticatorInfo,
  AuthResult,
  EmailAddressInfo,
  RecoveryCodesInfo,
  toAuthResult,
  TotpSetup,
} from './allauth';
import { ReauthenticationPrompt } from './reauthentication';
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
  private readonly reauthentication = inject(ReauthenticationPrompt);

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

  // --- 2FA (plan L1 §4.3, L1.6) ------------------------------------------------------------

  /** Étape 2FA de la connexion (flux `mfa_authenticate`) : code TOTP ou code de secours. */
  mfaAuthenticate(code: string): Promise<AuthResult> {
    return this.track(this.http.post<AllauthResponse>(this.url('auth/2fa/authenticate'), { code }));
  }

  /** Réauthentification par la 2FA : valide aussi la session pour la gestion (*step-up*). */
  mfaReauthenticate(code: string): Promise<AuthResult> {
    return this.track(
      this.http.post<AllauthResponse>(this.url('auth/2fa/reauthenticate'), { code }),
    );
  }

  async authenticators(): Promise<AuthenticatorInfo[]> {
    const result = await this.call(
      this.http.get<AllauthResponse>(this.url('account/authenticators')),
    );
    return Array.isArray(result.data) ? (result.data as AuthenticatorInfo[]) : [];
  }

  /**
   * Secret TOTP en attente (404 d'allauth avec `meta.secret`), ou `null` si la 2FA est déjà
   * active. 409 `unverified_email` : une adresse du compte n'est pas vérifiée.
   */
  async totpSetup(): Promise<{ setup: TotpSetup | null; result: AuthResult }> {
    const result = await this.call(
      this.http.get<AllauthResponse>(this.url('account/authenticators/totp')),
    );
    const meta = result.meta;
    const setup =
      result.status === 404 && meta?.secret && meta.totp_url
        ? { secret: meta.secret, totpUrl: meta.totp_url }
        : null;
    return { setup, result };
  }

  activateTotp(code: string): Promise<AuthResult> {
    return this.withReauthentication(() =>
      this.http.post<AllauthResponse>(this.url('account/authenticators/totp'), { code }),
    );
  }

  deactivateTotp(): Promise<AuthResult> {
    return this.withReauthentication(() =>
      this.http.delete<AllauthResponse>(this.url('account/authenticators/totp')),
    );
  }

  async recoveryCodes(): Promise<RecoveryCodesInfo | null> {
    const result = await this.withReauthentication(() =>
      this.http.get<AllauthResponse>(this.url('account/authenticators/recovery-codes')),
    );
    return result.status === 200 ? (result.data as RecoveryCodesInfo) : null;
  }

  async regenerateRecoveryCodes(): Promise<RecoveryCodesInfo | null> {
    const result = await this.withReauthentication(() =>
      this.http.post<AllauthResponse>(this.url('account/authenticators/recovery-codes'), {}),
    );
    return result.status === 200 ? (result.data as RecoveryCodesInfo) : null;
  }

  // --- Adresses e-mail (réauthentification récente exigée, §4.2) ----------------------------

  async emailAddresses(): Promise<EmailAddressInfo[]> {
    const result = await this.call(this.http.get<AllauthResponse>(this.url('account/email')));
    return Array.isArray(result.data) ? (result.data as EmailAddressInfo[]) : [];
  }

  addEmail(email: string): Promise<AuthResult> {
    return this.withReauthentication(() =>
      this.http.post<AllauthResponse>(this.url('account/email'), { email }),
    );
  }

  removeEmail(email: string): Promise<AuthResult> {
    return this.withReauthentication(() =>
      this.http.delete<AllauthResponse>(this.url('account/email'), { body: { email } }),
    );
  }

  makePrimaryEmail(email: string): Promise<AuthResult> {
    return this.withReauthentication(() =>
      this.http.patch<AllauthResponse>(this.url('account/email'), { email, primary: true }),
    );
  }

  /** Renvoi du lien de vérification d'une adresse secondaire. */
  resendEmailVerification(email: string): Promise<AuthResult> {
    return this.call(this.http.put<AllauthResponse>(this.url('account/email'), { email }));
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

  /**
   * Action protégée : sur un 401 portant le flux `reauthenticate` (session toujours
   * ouverte), ouvre la fenêtre de réauthentification puis rejoue l'appel **une seule fois**.
   */
  private async withReauthentication(
    request: () => Observable<AllauthResponse>,
  ): Promise<AuthResult> {
    const result = await this.call(request());
    const needsReauthentication =
      result.status === 401 &&
      result.authenticated &&
      (result.pendingFlow === 'reauthenticate' || result.pendingFlow === 'mfa_reauthenticate');
    if (needsReauthentication && (await this.reauthentication.prompt())) {
      return this.call(request());
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
