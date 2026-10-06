import type { Period, PublicCategory, PublicFee, Zone } from '@gestconf/shared';

export const PERIODS: readonly Period[] = ['early', 'regular', 'onsite'];
export const ZONES: readonly Zone[] = ['local', 'international'];

/** Texte dans la langue demandée, le français à défaut d'anglais. */
export function inLanguage(fr: string, en: string | undefined, lang: string): string {
  return (lang === 'en' && en) || fr;
}

/** Colonnes de la grille : couples (période, zone) proposés par au moins une catégorie. */
export function feeColumns(
  categories: readonly PublicCategory[],
): { period: Period; zone: Zone }[] {
  const offered = new Set(
    categories.flatMap((category) => category.fees.map((fee) => `${fee.period}:${fee.zone}`)),
  );
  return PERIODS.flatMap((period) =>
    ZONES.filter((zone) => offered.has(`${period}:${zone}`)).map((zone) => ({ period, zone })),
  );
}

export function feeFor(fees: readonly PublicFee[], period: Period, zone: Zone): PublicFee | null {
  return fees.find((fee) => fee.period === period && fee.zone === zone) ?? null;
}
