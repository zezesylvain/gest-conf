/**
 * Montant décimal transmis par l'API (« 25000.00 », chaîne pour ne rien perdre en virgule
 * flottante côté serveur) au format de la langue et de la devise (plan L6). Le franc CFA
 * n'a pas de décimales : `Intl` le sait (ISO 4217). Affichage seulement : les calculs
 * restent au serveur, en `Decimal`.
 */
export function formatMoney(
  amount: string | number | null | undefined,
  currency: string,
  lang: string,
): string {
  if (amount === null || amount === undefined || amount === '') {
    return '—';
  }
  return new Intl.NumberFormat(lang === 'en' ? 'en-GB' : 'fr-FR', {
    style: 'currency',
    currency,
  }).format(Number(amount));
}
