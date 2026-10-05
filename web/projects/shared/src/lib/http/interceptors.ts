import {
  HttpContextToken,
  HttpErrorResponse,
  HttpHandlerFn,
  HttpInterceptorFn,
  HttpRequest,
} from '@angular/common/http';
import { inject, InjectionToken } from '@angular/core';
import { catchError, EMPTY, endWith, ignoreElements, switchMap, throwError } from 'rxjs';

import { LanguageService } from '../i18n/language.service';
import { GcApiError, toApiError } from './api-error';

/** Préfixes servis par Django (même domaine, plan L1 §9). */
export const API_PREFIX = '/api/';
export const BUSINESS_API_PREFIX = '/api/v1/';
export const AUTH_API_PREFIX = '/api/_allauth/browser/v1/';

/** Une seule nouvelle tentative par requête (CSRF, plan §10.1). */
const RETRIED = new HttpContextToken<boolean>(() => false);

/**
 * Réaction à une session absente ou expirée sous `/api/v1/` : vider l'état puis
 * renvoyer vers la connexion (portail : navigation interne ; gestion : page entière).
 * Fournie par chaque application (`provideGestconfApi({ onSessionExpired })`).
 */
export const SESSION_EXPIRED_HANDLER = new InjectionToken<() => void>('SESSION_EXPIRED_HANDLER', {
  factory: () => () => undefined,
});

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
 *   une seule nouvelle tentative.
 */
export const sessionInterceptor: HttpInterceptorFn = (request, next) => {
  const onSessionExpired = inject(SESSION_EXPIRED_HANDLER);
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
      if (error.code === 'csrf_failed' && !request.context.get(RETRIED)) {
        return refreshCsrfCookie(next).pipe(
          switchMap(() => next(request.clone({ context: request.context.set(RETRIED, true) }))),
        );
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
