import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { ActiveContext, editionFromRoute, FORBIDDEN_PATH, MeStore } from '@gestconf/shared';

import { managedEditions } from './managed-editions';

/**
 * `/gestion/` : dernière édition utilisée si elle est encore accessible, sinon l'unique
 * édition gérée, sinon le sélecteur (plan L1 §10.3).
 */
export const lastEditionRedirect: CanActivateFn = () => {
  const router = inject(Router);
  const editions = managedEditions(inject(MeStore));
  const last = inject(ActiveContext).lastEditionId();
  const target =
    editions.find((edition) => edition.id === last) ?? (editions.length === 1 ? editions[0] : null);
  return router.createUrlTree(target ? ['/editions', target.id] : ['/editions']);
};

/**
 * `/gestion/editions/:id` : tableau de bord avec `edition.read`, sinon « Membres » avec
 * `members.read` (cas du président du CS si D8 n'est pas retenue), sinon « Mes évaluations »
 * avec `reviews.write` (relecteur), sinon accès refusé.
 */
export const editionHomeRedirect: CanActivateFn = (route) => {
  const router = inject(Router);
  const edition = editionFromRoute(inject(MeStore), route);
  if (edition?.capabilities.includes('edition.read')) {
    return router.createUrlTree(['/editions', edition.id, 'tableau-de-bord']);
  }
  if (edition?.capabilities.includes('members.read')) {
    return router.createUrlTree(['/editions', edition.id, 'comites', 'membres']);
  }
  // Relecteur (plan L4, H1) : « Mes évaluations ».
  if (edition?.capabilities.includes('reviews.write')) {
    return router.createUrlTree(['/editions', edition.id, 'evaluations']);
  }
  return router.parseUrl(FORBIDDEN_PATH);
};
