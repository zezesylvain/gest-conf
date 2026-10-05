import { DOCUMENT, inject, InjectionToken } from '@angular/core';
import { Router } from '@angular/router';

import { MeStore } from './me.store';
import { isManagementUrl, safeNext } from './safe-next';
import { SessionStore } from './session.store';

/** Route de connexion (portail, plan L1 D11). */
export const LOGIN_PATH = '/compte/connexion';

/**
 * Comment l'application rejoint la connexion : `router` (portail, même application) ou
 * `document` (gestion : la connexion est dans le portail, page entière).
 */
export const LOGIN_NAVIGATION = new InjectionToken<'router' | 'document'>('LOGIN_NAVIGATION', {
  factory: () => 'router',
});

/** URL de connexion avec la page à retrouver ensuite (`next` validé). */
export function loginUrl(next: string | null): string {
  const target = next ? safeNext(next, '') : '';
  return target ? `${LOGIN_PATH}?next=${encodeURIComponent(target)}` : LOGIN_PATH;
}

/**
 * Fabrique du traitement d'une session absente ou expirée sous `/api/v1/` (plan §10.4) :
 * vidage des stores, puis retour à la connexion avec `next`.
 */
export function sessionExpiredHandlerFactory(): () => void {
  const session = inject(SessionStore);
  const meStore = inject(MeStore);
  const navigation = inject(LOGIN_NAVIGATION);
  const router = inject(Router, { optional: true });
  const document = inject(DOCUMENT);
  return () => {
    session.clear({ expired: true });
    meStore.clear();
    const location = document.defaultView?.location;
    const current = location ? `${location.pathname}${location.search}` : null;
    const target = loginUrl(current);
    if (navigation === 'document' || !router) {
      location?.assign(target);
    } else if (!router.url.startsWith(LOGIN_PATH)) {
      void router.navigateByUrl(target);
    }
  };
}

/** Suite de la connexion : route interne du portail, ou page entière vers la gestion. */
export function navigateAfterLogin(router: Router, document: Document, next: unknown): void {
  const target = safeNext(next);
  if (isManagementUrl(target)) {
    document.defaultView?.location.assign(target);
  } else {
    void router.navigateByUrl(target);
  }
}
