/**
 * Date et heure d'un instant UTC dans un fuseau donné (celui de l'édition ou celui du
 * navigateur), avec l'abréviation du fuseau (plan L1 D13).
 *
 * Options détaillées : `dateStyle`/`timeStyle` ne se combinent pas avec `timeZoneName`
 * (ECMA-402 lève une TypeError).
 */
const OPTIONS: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  timeZoneName: 'short',
};

export function formatInZone(iso: string, timeZone: string | undefined, locale: string): string {
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) {
    return iso;
  }
  try {
    return new Intl.DateTimeFormat(locale, { ...OPTIONS, timeZone }).format(value);
  } catch {
    // Fuseau inconnu du navigateur : affichage en UTC, explicite.
    return new Intl.DateTimeFormat(locale, { ...OPTIONS, timeZone: 'UTC' }).format(value);
  }
}

/** `2027-03-31T23:59:00` → `2027-03-31T23:59` (valeur d'un champ datetime-local). */
export function toDateTimeLocalValue(atLocal: string): string {
  return atLocal.slice(0, 16);
}
