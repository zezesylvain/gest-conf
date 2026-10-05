import SITE_PAGES_JSON from './site-pages.json';

/** Langues du portail public : la langue est dans l'adresse (E2). */
export type SiteLanguage = 'fr' | 'en';
export const SITE_LANGUAGES: readonly SiteLanguage[] = ['fr', 'en'];

export interface SitePage {
  slug: string;
  fr: string;
  en: string;
  title_fr: string;
  title_en: string;
  coming_soon: boolean;
}

/**
 * Pages du site (plan L2 §2.2) : copie de ``apps.portal.site.SITE_PAGES`` (identité vérifiée
 * par un test du serveur). Adresses figées, gabarit codé ; les pages personnalisées vivent
 * sous ``/<langue>/p/<slug>/``.
 */
export const SITE_PAGES: readonly SitePage[] = SITE_PAGES_JSON;
export const SITE_PAGES_BY_SLUG: Readonly<Record<string, SitePage>> = Object.fromEntries(
  SITE_PAGES.map((page) => [page.slug, page]),
);

/** Adresse publique d'une page du site, avec barre finale (adresse canonique). */
export function sitePagePath(slug: string, language: SiteLanguage): string {
  const segment = SITE_PAGES_BY_SLUG[slug]?.[language] ?? '';
  return segment ? `/${language}/${segment}/` : `/${language}/`;
}

export function customPagePath(slug: string, language: SiteLanguage): string {
  return `/${language}/p/${slug}/`;
}

/** Valeur localisée d'un champ bilingue ; l'anglais vide se replie sur le français. */
export function localized<T extends object>(
  item: T,
  field: string,
  language: SiteLanguage,
): string {
  const record = item as Record<string, unknown>;
  const value = record[`${field}_${language}`];
  const fallback = record[`${field}_fr`];
  return (typeof value === 'string' && value) || (typeof fallback === 'string' ? fallback : '');
}
