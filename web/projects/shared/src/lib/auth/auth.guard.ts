import { inject } from '@angular/core';
import { CanMatchFn, Router, UrlSegment } from '@angular/router';

import { AuthApi } from './auth-api';
import { LOGIN_PATH } from './login-navigation';
import { SessionStore } from './session.store';

/**
 * Garde « connecté » (ergonomie seulement, règle n° 2 : le serveur vérifie toujours).
 * Amorce la session si son état est inconnu ; sinon renvoie vers la connexion avec `next`.
 */
export const authGuard: CanMatchFn = async (_route, segments: UrlSegment[]) => {
  const session = inject(SessionStore);
  const router = inject(Router);
  if (session.state() === 'unknown') {
    try {
      await inject(AuthApi).loadSession();
    } catch {
      session.clear();
    }
  }
  if (session.authenticated()) {
    return true;
  }
  const navigation = router.currentNavigation();
  const next =
    navigation?.extractedUrl.toString() ?? `/${segments.map((segment) => segment.path).join('/')}`;
  return router.createUrlTree([LOGIN_PATH], { queryParams: { next } });
};
