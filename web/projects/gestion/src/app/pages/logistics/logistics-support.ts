import { Diet, Equipment, MealKind, TravelMeans, VisitStatus } from '@gestconf/shared';

/** Catalogues fermés du serveur (plan L8, N6 à N8), dans l'ordre des écrans. */
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
export const VISIT_STATUSES: readonly VisitStatus[] = ['to_arrange', 'booked', 'confirmed'];
export const MEAL_KINDS: readonly MealKind[] = ['coffee_break', 'lunch', 'dinner', 'cocktail'];
export const DIETS: readonly Diet[] = [
  'vegetarian',
  'vegan',
  'no_pork',
  'gluten_free',
  'lactose_free',
  'other',
];

/**
 * Heure locale de l'édition renvoyée par le serveur (`AAAA-MM-JJTHH:MM`, D13) rendue
 * lisible, sans conversion de fuseau : c'est déjà l'heure du lieu.
 */
export function localLabel(value: string | null | undefined, lang: string): string {
  if (!value) return '—';
  const [day, time] = value.split('T');
  const date = new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'fr-FR', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
  return time ? `${date} ${time.slice(0, 5)}` : date;
}
