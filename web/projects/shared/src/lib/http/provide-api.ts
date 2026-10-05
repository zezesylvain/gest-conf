import { EnvironmentProviders, makeEnvironmentProviders } from '@angular/core';
import {
  provideHttpClient,
  withFetch,
  withInterceptors,
  withXsrfConfiguration,
} from '@angular/common/http';

import {
  LOGIN_NAVIGATION,
  mfaChallengeHandlerFactory,
  sessionExpiredHandlerFactory,
} from '../auth/login-navigation';
import {
  acceptLanguageInterceptor,
  apiErrorInterceptor,
  MFA_CHALLENGE_HANDLER,
  SESSION_EXPIRED_HANDLER,
  sessionInterceptor,
} from './interceptors';

export interface GestconfApiOptions {
  /**
   * Accès à la connexion après une session expirée : `router` (portail, défaut) ou
   * `document` (gestion : la connexion est dans le portail, page entière).
   */
  loginNavigation?: 'router' | 'document';
}

/**
 * Client HTTP de l'API GEST-CONF.
 *
 * Authentification par session Django + jeton CSRF (pas de JWT dans le navigateur) :
 * Angular lit le cookie « csrftoken » posé par Django et le renvoie dans l'en-tête
 * « X-CSRFToken » sur les requêtes modifiantes (POST, PUT, PATCH, DELETE).
 * L'URL racine (/api) provient du schéma OpenAPI (ApiConfiguration générée).
 *
 * Intercepteurs, du plus externe au plus interne : langue, session et CSRF, puis
 * normalisation des erreurs (`GcApiError`), que voit donc l'intercepteur de session.
 */
export function provideGestconfApi(options: GestconfApiOptions = {}): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideHttpClient(
      withFetch(),
      withXsrfConfiguration({ cookieName: 'csrftoken', headerName: 'X-CSRFToken' }),
      withInterceptors([acceptLanguageInterceptor, sessionInterceptor, apiErrorInterceptor]),
    ),
    { provide: LOGIN_NAVIGATION, useValue: options.loginNavigation ?? 'router' },
    { provide: SESSION_EXPIRED_HANDLER, useFactory: sessionExpiredHandlerFactory },
    { provide: MFA_CHALLENGE_HANDLER, useFactory: mfaChallengeHandlerFactory },
  ]);
}
