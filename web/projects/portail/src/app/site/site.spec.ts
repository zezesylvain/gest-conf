import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { GcApiError, PublicComposition, PublicSection, PublicSite } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { BehaviorSubject } from 'rxjs';

import { provideAccountTesting } from '../account/testing';
import { daysUntil } from './countdown';
import { PortalData } from './portal-data';
import { PortalPage } from './portal-page';
import { PageContext, PublicMenus } from './public-portal';
import { SectionsView } from './sections';
import { SiteNav } from './site-nav';
import { sitePagePath } from './site-pages';

const SITE: PublicSite = {
  edition: {
    code: 'GC27',
    slug: '2027',
    year: 2027,
    title_fr: 'GEST-CONF 2027',
    title_en: 'GEST-CONF 2027 (EN)',
    theme_fr: 'Science ouverte',
    theme_en: '',
    start_date: '2027-06-01',
    end_date: '2027-06-03',
    venue: 'Palais',
    city: 'Abidjan',
    country: 'CI',
    timezone: 'Africa/Abidjan',
    submission_languages: ['fr', 'en'],
    tracks: [{ code: 'ia', name_fr: 'IA', name_en: 'AI', description_fr: '', description_en: '' }],
    submission_types: [],
    key_dates: [
      {
        code: 'call_open',
        at: '2026-11-02T09:00:00Z',
        at_local: '2026-11-02T09:00:00',
        label_fr: '',
        label_en: '',
      },
    ],
  },
  poster: null,
  documents: [],
  committees: {
    scientific: { members: [], others: 0 },
    organizing: { members: [], others: 0 },
  },
  site_url: 'https://conf.example',
};

function section(overrides: Partial<PublicSection>): PublicSection {
  return {
    code: 's',
    section_type: 'rich_text',
    title_fr: 'Titre',
    title_en: '',
    subtitle_fr: '',
    subtitle_en: '',
    body_fr: '',
    body_en: '',
    cta_label_fr: '',
    cta_label_en: '',
    cta_url: '',
    cta2_label_fr: '',
    cta2_label_en: '',
    cta2_url: '',
    image: null,
    config: {},
    data: null,
    ...overrides,
  };
}

const COMPOSITION = (slug: string, sections: PublicSection[] = []): PublicComposition => ({
  page: {
    slug,
    is_system: slug !== 'infos',
    title_fr: slug === 'infos' ? 'Infos pratiques' : 'Appel modifié',
    title_en: '',
    description_fr: 'Description de la page',
    description_en: '',
    paths: { fr: `/fr/p/${slug}/`, en: `/en/p/${slug}/` },
  },
  sections,
});

async function renderPage(
  data: Record<string, unknown>,
  params: Record<string, string> = {},
  page?: () => Promise<PublicComposition>,
) {
  const portal = {
    page: vi.fn(page ?? (() => Promise.resolve(COMPOSITION('call')))),
    site: vi.fn().mockResolvedValue(SITE),
  };
  TestBed.configureTestingModule({
    providers: [
      ...provideAccountTesting(),
      { provide: PortalData, useValue: portal },
      {
        provide: ActivatedRoute,
        useValue: {
          snapshot: { data, paramMap: convertToParamMap(params) },
          paramMap: new BehaviorSubject(convertToParamMap(params)),
        },
      },
    ],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(PortalPage);
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, root: fixture.nativeElement as HTMLElement, portal };
}

describe('PortalPage', () => {
  it('page du site : gabarit, titre en base, marqueur de rendu, contexte de langue', async () => {
    const { root } = await renderPage({ lang: 'fr', slug: 'call' });
    expect(root.querySelector('h1')?.textContent).toBe('Appel modifié');
    expect(root.querySelector('[data-gc-rendered]')?.getAttribute('data-gc-rendered')).toBe(
      'fr:call',
    );
    expect(root.textContent).toContain('Formats de communication');
    expect(TestBed.inject(PageContext).paths()).toEqual({ fr: '/fr/appel/', en: '/en/call/' });
    expect(document.title).toBe('Appel modifié · GEST-CONF 2027');
    expect(document.head.querySelector('link[rel=canonical]')?.getAttribute('href')).toBe(
      'https://conf.example/fr/appel/',
    );
  });

  it('page du site sans composition (404) : gabarit seul, page complète', async () => {
    const { root } = await renderPage({ lang: 'en', slug: 'tracks' }, {}, () =>
      Promise.reject(new GcApiError(404, 'not_found', '')),
    );
    expect(root.querySelector('[data-gc-rendered]')?.getAttribute('data-gc-rendered')).toBe(
      'en:tracks',
    );
    expect(root.textContent).toContain('AI');
  });

  it('page personnalisée inconnue : « page introuvable », sans marqueur', async () => {
    const { root } = await renderPage({ lang: 'fr', custom: true }, { slug: 'inconnue' }, () =>
      Promise.reject(new GcApiError(404, 'not_found', '')),
    );
    expect(root.querySelector('[data-gc-rendered]')).toBeNull();
    expect(root.textContent).toContain("Cette page n'existe pas.");
  });

  it('API en erreur : message, sans marqueur (le contrôle après build refuse la page)', async () => {
    const { root } = await renderPage({ lang: 'fr', slug: 'home' }, {}, () =>
      Promise.reject(new GcApiError(500, 'server_error', '')),
    );
    expect(root.querySelector('[data-gc-rendered]')).toBeNull();
    expect(root.textContent).toContain('momentanément indisponible');
  });

  it('page personnalisée : titre de la page et sections', async () => {
    const { root, portal } = await renderPage({ lang: 'fr', custom: true }, { slug: 'infos' }, () =>
      Promise.resolve(
        COMPOSITION('infos', [section({ code: 'acces', body_fr: '<p>Bus <b>12</b></p>' })]),
      ),
    );
    expect(portal.page).toHaveBeenCalledWith('infos');
    expect(root.querySelector('h1')?.textContent).toBe('Infos pratiques');
    expect(root.querySelector('[data-section=acces] .prose')?.innerHTML).toBe(
      '<p>Bus <strong>12</strong></p>',
    );
  });
});

describe('SectionsView', () => {
  async function render(sections: PublicSection[], language: 'fr' | 'en' = 'fr') {
    TestBed.configureTestingModule({ providers: provideAccountTesting() });
    await useTestLanguage(language);
    const fixture = TestBed.createComponent(SectionsView);
    fixture.componentRef.setInput('sections', sections);
    fixture.componentRef.setInput('language', language);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('HTML réassaini au rendu, type inconnu ignoré', async () => {
    const root = await render([
      section({ code: 'a', body_fr: '<p onclick="x()">ok<script>alert(1)</script></p>' }),
      section({ code: 'b', section_type: 'carrousel' as PublicSection['section_type'] }),
    ]);
    expect(root.querySelector('[data-section=a] .prose')?.innerHTML).toBe('<p>ok</p>');
    expect(root.querySelector('[data-section=b]')).toBeNull();
  });

  it('comité (E5) : membres consentants, liens https seulement, autres membres comptés', async () => {
    const member = {
      title: 'pr' as const,
      name: 'Koffi Yao',
      chair: true,
      function: '' as const,
      institution: 'Univ. FHB',
      country: 'CI',
      website: 'https://koffi.example',
      scholar_url: 'javascript:alert(1)',
      linkedin_url: '',
      photo_url: '/api/v1/public/files/u/photo.jpg',
    };
    const root = await render([
      section({
        code: 'sc',
        section_type: 'committee',
        data: { members: [member], others: 2 },
      }),
    ]);
    const item = root.querySelector('[data-section=sc] .people li') as HTMLElement;
    expect(item.querySelector('h3')?.textContent?.replace(/\s+/g, ' ').trim()).toBe('Pr Koffi Yao');
    expect(item.querySelector('.role')?.textContent?.trim()).toBe('Présidence');
    expect(item.textContent).toContain('Univ. FHB, Côte d’Ivoire');
    expect(
      Array.from(item.querySelectorAll('.links a')).map((a) => a.getAttribute('href')),
    ).toEqual(['https://koffi.example']);
    expect(
      root.querySelector('[data-section=sc] portail-committee-list > p.muted')?.textContent?.trim(),
    ).toBe('et 2 autres membres');
  });

  it('anglais vide : repli sur le français ; boutons seulement complets', async () => {
    const root = await render(
      [
        section({
          code: 'c',
          section_type: 'cta_banner',
          title_fr: 'Soumettre',
          cta_label_fr: 'Appel',
          cta_url: '/en/call/',
          cta2_label_fr: 'Sans lien',
        }),
      ],
      'en',
    );
    expect(root.querySelector('h2')?.textContent).toBe('Soumettre');
    expect(Array.from(root.querySelectorAll('.button')).map((a) => a.textContent?.trim())).toEqual([
      'Appel',
    ]);
  });
});

describe('SiteNav', () => {
  async function render(items: unknown[]) {
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: PublicMenus, useValue: { menu: vi.fn().mockResolvedValue(items) } },
      ],
    });
    await useTestLanguage('en');
    TestBed.inject(PageContext).set('en', { fr: '/fr/', en: '/en/' });
    const fixture = TestBed.createComponent(SiteNav);
    fixture.componentRef.setInput('location', 'header');
    await fixture.whenStable();
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('menu vide : repli sur la navigation codée (dans la langue de l’adresse)', async () => {
    const root = await render([]);
    const links = Array.from(root.querySelectorAll('a'));
    expect(links[0].textContent?.trim()).toBe('Call for papers');
    expect(links[0].getAttribute('href')).toBe('/en/call');
  });

  it('menu géré : libellés et adresses de la langue, lien externe en nouvel onglet', async () => {
    const root = await render([
      {
        label_fr: 'Contact',
        label_en: 'Contact us',
        href_fr: 'mailto:a@b.c',
        href_en: 'mailto:a@b.c',
        new_tab: false,
        page: null,
      },
      {
        label_fr: 'Site',
        label_en: '',
        href_fr: 'https://x.example',
        href_en: 'https://x.example',
        new_tab: true,
        page: null,
      },
    ]);
    const links = Array.from(root.querySelectorAll('a'));
    expect(links.map((a) => a.textContent?.trim())).toEqual(['Contact us', 'Site']);
    expect(links[1].getAttribute('target')).toBe('_blank');
    expect(links[1].getAttribute('rel')).toBe('noopener');
  });
});

describe('daysUntil (E8)', () => {
  it('compte les jours civils dans le fuseau de l’édition', () => {
    const now = new Date('2027-05-31T23:30:00Z');
    expect(daysUntil('2027-06-01', 'Africa/Abidjan', now)).toBe(1);
    // À Tokyo (UTC+9), le 1er juin est déjà commencé.
    expect(daysUntil('2027-06-01', 'Asia/Tokyo', now)).toBe(0);
  });
});

describe('sitePagePath', () => {
  it('adresses figées avec barre finale', () => {
    expect(sitePagePath('home', 'fr')).toBe('/fr/');
    expect(sitePagePath('call', 'en')).toBe('/en/call/');
  });
});
