import { apiErrorMessage, Diet, Equipment, GcApiError, TravelMeans } from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';

/** Catalogues fermés du serveur (plan L8, N6, N7), dans l'ordre des écrans. */
export const DIETS: readonly Diet[] = [
  'vegetarian',
  'vegan',
  'no_pork',
  'gluten_free',
  'lactose_free',
  'other',
];
export const EQUIPMENT: readonly Equipment[] = [
  'projector',
  'microphone',
  'sound_system',
  'computer',
  'whiteboard',
  'interpretation',
  'recording',
  'wifi',
];
export const TRAVEL_MEANS: readonly TravelMeans[] = ['plane', 'train', 'road', 'other'];
export const ALLERGIES_MAX = 200;

/** Message d'une erreur d'API suivi des erreurs de champ du serveur, pour le résumé. */
export function messagesOf(translate: TranslateService, error: unknown): string[] {
  const fields = error instanceof GcApiError ? Object.values(error.fields).flat() : [];
  return [apiErrorMessage(translate, error), ...fields];
}
