import { PublicEdition, PublicFileRef } from '@gestconf/shared';

import { localized, SiteLanguage } from './site-pages';

/**
 * Référencement d'une page publique (plan L2, E7) : adresse canonique (barre finale), variantes
 * de langue (`hreflang`, `x-default` → français), Open Graph (affiche de l'édition) et, sur
 * l'accueil, un JSON-LD `Event`. Écrit dans `<head>` au pré-rendu ; chaque appel remplace
 * les éléments du précédent (marqués `data-gc-seo`).
 *
 * Le JSON-LD n'est pas exécutable : la CSP à empreintes l'ignore (`inject-csp.mjs`).
 */
export interface SeoInput {
  /** Origine publique, sans barre finale (`site_url` de l'API). */
  siteUrl: string;
  language: SiteLanguage;
  /** Adresses de la page dans les deux langues, avec barre finale. */
  paths: Record<SiteLanguage, string>;
  title: string;
  description: string;
  edition: PublicEdition;
  poster: PublicFileRef | null;
  /** JSON-LD `Event` (accueil). */
  event: boolean;
}

const MARK = 'data-gc-seo';
const LOCALES: Record<SiteLanguage, string> = { fr: 'fr_FR', en: 'en_GB' };

function absolute(siteUrl: string, path: string): string {
  return /^https?:\/\//.test(path) ? path : `${siteUrl}${path}`;
}

/** Objet schema.org `Event` ; `null` sans date de début (exigée par les moteurs). */
export function eventJsonLd(input: SeoInput): Record<string, unknown> | null {
  const { edition, language, siteUrl } = input;
  if (!edition.start_date) return null;
  const place = edition.venue || edition.city;
  return {
    '@context': 'https://schema.org',
    '@type': 'Event',
    name: localized(edition, 'title', language),
    ...(localized(edition, 'theme', language)
      ? { description: localized(edition, 'theme', language) }
      : {}),
    startDate: edition.start_date,
    endDate: edition.end_date ?? edition.start_date,
    eventStatus: 'https://schema.org/EventScheduled',
    url: absolute(siteUrl, input.paths[language]),
    inLanguage: language,
    ...(place
      ? {
          location: {
            '@type': 'Place',
            name: edition.venue || edition.city,
            address: {
              '@type': 'PostalAddress',
              ...(edition.city ? { addressLocality: edition.city } : {}),
              ...(edition.country ? { addressCountry: edition.country } : {}),
            },
          },
        }
      : {}),
    ...(input.poster ? { image: [absolute(siteUrl, input.poster.url)] } : {}),
  };
}

/** JSON sûr dans un `<script>` : aucun `<` (donc ni `</script>` ni `<!--`). */
export function scriptSafeJson(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026');
}

/** Retire les éléments posés par `applySeo` (page introuvable, sortie du site public). */
export function clearSeo(doc: Document): void {
  doc.head.querySelectorAll(`[${MARK}]`).forEach((element) => element.remove());
}

export function applySeo(doc: Document, input: SeoInput): void {
  const head = doc.head;
  clearSeo(doc);
  const add = (tag: string, attributes: Record<string, string>, text?: string) => {
    const element = doc.createElement(tag);
    element.setAttribute(MARK, '');
    for (const [name, value] of Object.entries(attributes)) {
      element.setAttribute(name, value);
    }
    if (text !== undefined) element.textContent = text;
    head.appendChild(element);
  };
  const { siteUrl, language, paths } = input;
  const url = absolute(siteUrl, paths[language]);
  add('link', { rel: 'canonical', href: url });
  add('link', { rel: 'alternate', hreflang: 'fr', href: absolute(siteUrl, paths.fr) });
  add('link', { rel: 'alternate', hreflang: 'en', href: absolute(siteUrl, paths.en) });
  add('link', { rel: 'alternate', hreflang: 'x-default', href: absolute(siteUrl, paths.fr) });
  const og: [string, string][] = [
    ['og:type', 'website'],
    ['og:url', url],
    ['og:title', input.title],
    ['og:site_name', localized(input.edition, 'title', language)],
    ['og:locale', LOCALES[language]],
    ['og:locale:alternate', LOCALES[language === 'fr' ? 'en' : 'fr']],
  ];
  if (input.description) og.push(['og:description', input.description]);
  const poster = input.poster;
  if (poster) {
    og.push(['og:image', absolute(siteUrl, poster.url)]);
    if (poster.width && poster.height) {
      og.push(['og:image:width', String(poster.width)], ['og:image:height', String(poster.height)]);
    }
  }
  for (const [property, content] of og) {
    add('meta', { property, content });
  }
  add('meta', { name: 'twitter:card', content: poster ? 'summary_large_image' : 'summary' });
  const event = input.event ? eventJsonLd(input) : null;
  if (event) {
    add('script', { type: 'application/ld+json' }, scriptSafeJson(event));
  }
}
