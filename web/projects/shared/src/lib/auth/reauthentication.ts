import { Injectable } from '@angular/core';

/**
 * Ouvre la fenêtre de réauthentification (mot de passe ou code 2FA) et résout `true` si la
 * personne s'est réauthentifiée, `false` si elle a renoncé.
 */
export type ReauthenticationOpener = () => Promise<boolean>;

/**
 * Point de rencontre entre la fenêtre de réauthentification, fournie par l'application
 * (portail : espace compte ; gestion : coque, L1.7), et ceux qui en ont besoin :
 * l'intercepteur (403 `reauthentication_required` de DRF) et `AuthApi` (401 portant le
 * flux `reauthenticate` d'allauth). Dans les deux cas, la requête est rejouée une seule
 * fois (plan L1 §4.3, §10.1). Sans fenêtre enregistrée, l'erreur remonte telle quelle.
 */
@Injectable({ providedIn: 'root' })
export class ReauthenticationPrompt {
  private opener: ReauthenticationOpener | null = null;
  private pending: Promise<boolean> | null = null;

  /** Enregistre la fenêtre ; renvoie la fonction de désinscription. */
  register(opener: ReauthenticationOpener): () => void {
    this.opener = opener;
    return () => {
      if (this.opener === opener) {
        this.opener = null;
      }
    };
  }

  /** Une seule fenêtre à la fois : des demandes simultanées partagent la même réponse. */
  prompt(): Promise<boolean> {
    if (!this.opener) {
      return Promise.resolve(false);
    }
    if (!this.pending) {
      this.pending = this.opener().finally(() => (this.pending = null));
    }
    return this.pending;
  }
}
