import {
  HttpContextToken,
  HttpErrorResponse,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject, InjectionToken } from '@angular/core';
import { catchError, EMPTY, endWith, from, ignoreElements, switchMap, throwError } from 'rxjs';

import { ReauthenticationPrompt } from '../auth/reauthentication';
import { LanguageService } from '../i18n/language.service';
import { GcApiError, toApiError } from './api-error';

/** Préfixes servis par Django (même domaine, plan L1 §9). */
export const API_PREFIX = '/api/';
export const BUSINESS_API_PREFIX = '/api/v1/';
export const AUTH_API_PREFIX = '/api/_allauth/browser/v1/';

/** Une seule nouvelle tentative par requête (CSRF ou réauthentification, plan §10.1). */
const RETRIED = new HttpContextToken<boolean>(() => false);

/**
 * Réaction à une session absente ou expirée sous `/api/v1/` : vider l'état puis
 * renvoyer vers la connexion (portail : navigation interne ; gestion : page entière).
 * Fournie par chaque application (`provideGestconfApi({ onSessionExpired })`).
 */
export const SESSION_EXPIRED_HANDLER = new InjectionToken<() => void>('SESSION_EXPIRED_HANDLER', {
  factory: () => () => undefined,
});

/** Codes de `MfaVerified` (plan L1 §4.4) : 2FA à activer, ou à valider dans la session. */
export type MfaChallenge = 'mfa_required' | 'mfa_enrollment_required';

/**
 * Réaction à un refus 2FA d'une route de gestion : renvoi vers
 * `/compte/double-authentification` (`mfa_required`) ou `/compte/securite`
 * (`mfa_enrollment_required`), avec `next`. Fournie par `provideGestconfApi`.
 */
export const MFA_CHALLENGE_HANDLER = new InjectionToken<(challenge: MfaChallenge) => void>(
  'MFA_CHALLENGE_HANDLER',
  { factory: () => () => undefined },
);

function pathOf(url: string): string {
  try {
    return new URL(url, 'http://local').pathname;
  } catch {
    return url;
  }
}

function isApiRequest(request: HttpRequest<unknown>): boolean {
  return pathOf(request.url).startsWith(API_PREFIX);
}

/** Langue courante dans `Accept-Language` : messages d'erreur et langue du compte à l'inscription. */
export const acceptLanguageInterceptor: HttpInterceptorFn = (request, next) => {
  if (!isApiRequest(request) || request.headers.has('Accept-Language')) {
    return next(request);
  }
  const language = inject(LanguageService).current();
  return next(request.clone({ setHeaders: { 'Accept-Language': language } }));
};

/** Convertit les réponses d'erreur de l'API (DRF et allauth) en `GcApiError`. */
export const apiErrorInterceptor: HttpInterceptorFn = (request, next) => {
  if (!isApiRequest(request)) {
    return next(request);
  }
  return next(request).pipe(
    catchError((error: unknown) =>
      throwError(() => (error instanceof HttpErrorResponse ? toApiError(error) : error)),
    ),
  );
};

/**
 * Session et CSRF (plan L1 §10.1) :
 * - **401 sous `/api/v1/` seulement** : session absente ou expirée (y compris la limite de
 *   12 h) → `SESSION_EXPIRED_HANDLER`. Sous `/api/_allauth/`, un 401 fait partie du
 *   protocole (amorçage, `verify_email`, `reauthenticate`…) : il est laissé à `AuthApi` ;
 * - **403 `csrf_failed`** : `GET auth/session` (qui repose le cookie `csrftoken`), puis
 *   une seule nouvelle tentative ;
 * - **403 `reauthentication_required`** : fenêtre de réauthentification
 *   (`ReauthenticationPrompt`), puis une seule nouvelle tentative si elle aboutit ;
 * - **403 `mfa_required` / `mfa_enrollment_required`** : `MFA_CHALLENGE_HANDLER`, puis
 *   l'erreur remonte (la page appelante n'affiche rien de plus).
 */
export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  const onSessionExpired = inject(SESSION_EXPIRED_HANDLER);
  const onMfaChallenge = inject(MFA_CHALLENGE_HANDLER);
  const reauthentication = inject(ReauthenticationPrompt);
  return next(request).pipe(
    catchError((error: unknown) => {
      if (!(error instanceof GcApiError)) {
        return throwError(() => error);
      }
      const path = pathOf(request.url);
      if (error.status === 401 && path.startsWith(BUSINESS_API_PREFIX)) {
        onSessionExpired();
        return throwError(() => error);
      }
      const retry = () => next(request.clone({ context: request.context.set(RETRIED, true) }));
      if (error.code === 'csrf_failed' && !request.context.get(RETRIED)) {
        return refreshCsrfCookie(next).pipe(switchMap(retry));
      }
      if (error.code === 'reauthentication_required' && !request.context.get(RETRIED)) {
        return from(reauthentication.prompt()).pipe(
          switchMap((done) => (done ? retry() : throwError(() => error))),
        );
      }
      if (error.code === 'mfa_required' || error.code === 'mfa_enrollment_required') {
        onMfaChallenge(error.code);
      }
      return throwError(() => error);
    }),
  );
};

function refreshCsrfCookie(next: HttpHandlerFn) {
  // Attendre la FIN de l'amorçage : son premier événement (« Sent ») déclencherait sinon la
  // nouvelle tentative avant que le cookie soit posé. 401 attendu pour un visiteur
  // anonyme : seul le cookie compte, l'erreur est ignorée.
  return next(new HttpRequest('GET', `${AUTH_API_PREFIX}auth/session`)).pipe(
    ignoreElements(),
    catchError(() => EMPTY),
    endWith(null),
  );
}
