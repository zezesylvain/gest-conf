import { PublicEdition } from '@gestconf/shared';

import { applySeo, clearSeo, eventJsonLd, scriptSafeJson, SeoInput } from './seo';

const EDITION = {
  code: 'GC27',
  title_fr: 'GEST-CONF 2027',
  title_en: 'GEST-CONF 2027 (EN)',
  theme_fr: 'Science </script> ouverte',
  theme_en: '',
  start_date: '2027-06-01',
  end_date: '2027-06-03',
  venue: 'Palais',
  city: 'Abidjan',
  country: 'CI',
} as PublicEdition;

const INPUT: SeoInput = {
  siteUrl: 'https://conf.example',
  language: 'en',
  paths: { fr: '/fr/appel/', en: '/en/call/' },
  title: 'Call for papers',
  description: 'Submit',
  edition: EDITION,
  poster: {
    url: '/api/v1/public/files/u/affiche.png',
    width: 1200,
    height: 630,
  } as SeoInput['poster'],
  event: true,
};

describe('Référencement (E7)', () => {
  afterEach(() => clearSeo(document));

  it('canonique avec barre finale, variantes de langue, Open Graph avec l’affiche', () => {
    applySeo(document, INPUT);
    const head = document.head;
    expect(head.querySelector('link[rel=canonical]')?.getAttribute('href')).toBe(
      'https://conf.example/en/call/',
    );
    const alternates = Array.from(head.querySelectorAll('link[rel=alternate]')).map(
      (link) => `${link.getAttribute('hreflang')} ${link.getAttribute('href')}`,
    );
    expect(alternates).toEqual([
      'fr https://conf.example/fr/appel/',
      'en https://conf.example/en/call/',
      'x-default https://conf.example/fr/appel/',
    ]);
    const og = (property: string) =>
      head.querySelector(`meta[property="${property}"]`)?.getAttribute('content');
    expect(og('og:image')).toBe('https://conf.example/api/v1/public/files/u/affiche.png');
    expect(og('og:locale')).toBe('en_GB');
    expect(og('og:site_name')).toBe('GEST-CONF 2027 (EN)');
  });

  it('chaque application remplace la précédente ; clearSeo retire tout', () => {
    applySeo(document, INPUT);
    applySeo(document, { ...INPUT, language: 'fr', event: false });
    expect(document.head.querySelectorAll('link[rel=canonical]').length).toBe(1);
    expect(document.head.querySelector('script[type="application/ld+json"]')).toBeNull();
    clearSeo(document);
    expect(document.head.querySelector('[data-gc-seo]')).toBeNull();
  });

  it('JSON-LD Event : sans « < » littéral, relu à l’identique', () => {
    applySeo(document, INPUT);
    const script = document.head.querySelector('script[type="application/ld+json"]');
    expect(script?.textContent).not.toContain('<');
    const event = JSON.parse(script?.textContent ?? '{}');
    expect(event).toMatchObject({
      '@type': 'Event',
      name: 'GEST-CONF 2027 (EN)',
      description: 'Science </script> ouverte', // repli sur le français
      startDate: '2027-06-01',
      endDate: '2027-06-03',
      url: 'https://conf.example/en/call/',
      location: { name: 'Palais', address: { addressLocality: 'Abidjan', addressCountry: 'CI' } },
    });
  });

  it('sans date de début : pas de JSON-LD', () => {
    expect(eventJsonLd({ ...INPUT, edition: { ...EDITION, start_date: null } })).toBeNull();
    expect(scriptSafeJson({ a: '<!--&>' })).toBe('{"a":"\\u003c!--\\u0026\\u003e"}');
  });
});
