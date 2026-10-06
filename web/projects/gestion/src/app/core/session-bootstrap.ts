import { DOCUMENT, inject, Injectable } from '@angular/core';
import { AuthApi, loginUrl, MeStore, SessionStore } from '@gestconf/shared';

import { Connectivity, isUnreachable } from './reception';

/**
 * Démarrage de la gestion (plan L1 §10.4, D11) : `GET auth/session` (pose aussi le cookie
 * CSRF), puis `GET /v1/me`. Sans session, redirection de page entière vers la connexion du
 * portail, avec la page demandée en `next`. Pas d'écran de connexion dans la gestion.
 *
 * Sans réseau (plan L7, K5), pas de redirection : la page de connexion ne serait pas
 * joignable ; l'écran d'accueil installé travaille alors sur la liste de l'appareil.
 */
@Injectable({ providedIn: 'root' })
export class SessionBootstrap {
  private readonly authApi = inject(AuthApi);
  private readonly session = inject(SessionStore);
  private readonly meStore = inject(MeStore);
  private readonly document = inject(DOCUMENT);
  private readonly connectivity = inject(Connectivity);

  async start(): Promise<void> {
    try {
      await this.authApi.loadSession();
    } catch (error) {
      if (isUnreachable(error)) {
        this.connectivity.startedOffline.set(true);
        return;
      }
      this.session.clear();
    }
    if (!this.session.authenticated()) {
      this.redirectToLogin();
      return;
    }
    try {
      await this.meStore.load();
    } catch {
      // 401 : déjà traité par l'intercepteur (session expirée) ; sinon, page d'erreur.
    }
  }

  private redirectToLogin(): void {
    const location = this.document.defaultView?.location;
    if (location) {
      location.assign(loginUrl(`${location.pathname}${location.search}`));
    }
  }
}
