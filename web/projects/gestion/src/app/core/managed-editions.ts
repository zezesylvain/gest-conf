import { MeEdition, MeStore } from '@gestconf/shared';

/** Éditions où le compte détient au moins une capacité de gestion (sélecteur, D3). */
export function managedEditions(meStore: MeStore): MeEdition[] {
  return (meStore.me()?.editions ?? []).filter((edition) => edition.capabilities.length > 0);
}

/** Titre d'une édition dans la langue courante (repli sur le français, D14). */
export function editionTitle(
  edition: { title_fr: string; title_en?: string },
  language: string,
): string {
  return language === 'en' && edition.title_en ? edition.title_en : edition.title_fr;
}
