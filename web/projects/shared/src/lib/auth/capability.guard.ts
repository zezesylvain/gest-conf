import { inject } from '@angular/core';
import { ActivatedRouteSnapshot, CanActivateFn, Router } from '@angular/router';

import { Capability } from '../api/models/capability';
import { MeEdition } from '../api/models/me-edition';
import { MeStore } from './me.store';

/** Chemin de la page « accès refusé » de la gestion. */
export const FORBIDDEN_PATH = '/acces-refuse';

/** Édition de `/me` correspondant au paramètre `editionId` de la route (ou de ses parents). */
export function editionFromRoute(
  meStore: MeStore,
  route: ActivatedRouteSnapshot,
): MeEdition | undefined {
  let current: ActivatedRouteSnapshot | null = route;
  let id: string | null = null;
  while (current && id === null) {
    id = current.paramMap.get('editionId');
    current = current.parent;
  }
  return meStore.me()?.editions.find((edition) => String(edition.id) === id);
}

/**
 * Garde de capacité dans l'édition de la route (ergonomie seulement, règle n° 2 : chaque
 * endpoint revérifie). Charge `/me` si besoin ; sinon renvoie vers « accès refusé ».
 */
export function capabilityGuard(...capabilities: Capability[]): CanActivateFn {
  return async (route) => {
    const meStore = inject(MeStore);
    const router = inject(Router);
    if (!meStore.loaded()) {
      try {
        await meStore.load();
      } catch {
        return router.parseUrl(FORBIDDEN_PATH);
      }
    }
    const edition = editionFromRoute(meStore, route);
    const allowed =
      edition !== undefined &&
      capabilities.every((capability) => edition.capabilities.includes(capability));
    return allowed || router.parseUrl(FORBIDDEN_PATH);
  };
}
