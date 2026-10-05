import { FormGroup } from '@angular/forms';
import {
  Capability,
  GcApiError,
  MeStore,
  apiErrorMessage,
  applyServerErrors,
} from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';

/** Capacités du compte dans une édition (`/me`), pour adapter l'interface seulement. */
export function editionCapabilities(meStore: MeStore, editionId: string | number): Capability[] {
  return (
    meStore.me()?.editions.find((edition) => String(edition.id) === String(editionId))
      ?.capabilities ?? []
  );
}

/**
 * Messages d'une erreur d'API : erreurs de champ posées sur le formulaire (s'il est
 * fourni), le reste pour le résumé. Les refus 2FA et de réauthentification sont déjà
 * traités par l'intercepteur ; leur message reste affiché.
 */
export function errorMessages(
  translate: TranslateService,
  error: unknown,
  form?: FormGroup,
): string[] {
  if (error instanceof GcApiError && form && Object.keys(error.fields).length) {
    const unplaced = applyServerErrors(form, error);
    return unplaced.length ? unplaced : [];
  }
  if (error instanceof GcApiError && Object.keys(error.fields).length) {
    return [apiErrorMessage(translate, error), ...Object.values(error.fields).flat()];
  }
  // Conflit (409) : le message du serveur, dans la langue de la requête, dit ce qui bloque
  // (« Fichier utilisé (section visuel, affiche) ») ; le libellé générique du code ne le dit pas.
  if (error instanceof GcApiError && error.status === 409 && error.message) {
    return [error.message];
  }
  return [apiErrorMessage(translate, error)];
}
