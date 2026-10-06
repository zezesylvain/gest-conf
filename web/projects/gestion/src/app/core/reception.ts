import { DOCUMENT, inject, Injectable, isDevMode, signal } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { ActiveContext, anyCapabilityGuard, GcApiError, MeStore } from '@gestconf/shared';

/**
 * Démarrage sans réseau de l'écran d'accueil installé (plan L7, K5). Seul cet écran sait
 * travailler hors ligne, sur la liste de l'appareil ; les autres écrans affichent leur
 * erreur habituelle.
 */
@Injectable({ providedIn: 'root' })
export class Connectivity {
  /** La session n'a pas pu être lue faute de réseau : `/me` est inconnu. */
  readonly startedOffline = signal(false);
}

/**
 * Serveur injoignable : pas de réseau (statut 0), ou passerelle en échec (502 à 504). Une
 * page contrôlée par le service worker d'Angular ne voit jamais le statut 0 : sans réseau,
 * le service worker répond lui-même 504 (constaté au navigateur, L7.6).
 */
export function isUnreachable(error: unknown): boolean {
  return error instanceof GcApiError && [0, 502, 503, 504].includes(error.status);
}

/** Chemin de l'accueil d'une édition (adresse annoncée par le plan, K5). */
export function receptionPath(editionId: number | string): string {
  return `/editions/${editionId}/accueil`;
}

/**
 * Garde de l'accueil : `checkin.scan` dans l'édition, ou présidence de séance (l'écran
 * s'ouvre alors en mode « session », sur ses sessions seulement, K7) ; ergonomie, règle
 * n° 2. Démarré hors ligne, `/me` est inaccessible : l'écran s'ouvre sur la liste de
 * l'appareil, et chaque pointage sera revérifié par le serveur à la synchronisation.
 */
export const receptionGuard: CanActivateFn = (route, state) => {
  if (inject(Connectivity).startedOffline() && !inject(MeStore).loaded()) {
    return true;
  }
  return anyCapabilityGuard('checkin.scan', 'sessions.chair')(route, state);
};

/**
 * `/gestion/accueil` : adresse de démarrage de l'application installée (manifeste) ; elle
 * mène à l'accueil de la dernière édition utilisée, connue même sans réseau.
 */
export const receptionRedirect: CanActivateFn = () => {
  const router = inject(Router);
  const last = inject(ActiveContext).lastEditionId();
  return router.parseUrl(last ? receptionPath(last) : '/editions');
};

const MANIFEST_ID = 'gestion-reception-manifest';

/**
 * Rend l'accueil installable (plan L7, K5 ; bilan de L7.0) : le manifeste est ajouté par cet
 * écran seul, et le service worker n'est enregistré que d'ici. Les autres utilisateurs de la
 * gestion n'en reçoivent jamais. En développement (`ng serve`), pas de service worker.
 */
@Injectable({ providedIn: 'root' })
export class ReceptionInstaller {
  private readonly document = inject(DOCUMENT);

  async install(): Promise<boolean> {
    if (!this.document.getElementById(MANIFEST_ID)) {
      const link = this.document.createElement('link');
      link.id = MANIFEST_ID;
      link.rel = 'manifest';
      link.href = 'manifest.webmanifest';
      this.document.head.appendChild(link);
    }
    const container = this.document.defaultView?.navigator.serviceWorker;
    if (!container || isDevMode()) {
      return false;
    }
    try {
      await container.register('ngsw-worker.js', { scope: './' });
      return true;
    } catch {
      return false;
    }
  }
}
