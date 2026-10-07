import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { GcApiError } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../../account/testing';
import { SiteBanner } from '../banner/site-banner';
import { CommunityData } from './community-data';
import { NewsOverview } from './news-overview';
import { SpeakersOverview } from './speakers-overview';
import { SponsorsOverview } from './sponsors-overview';

const SPACES = new RegExp('[' + String.fromCharCode(0xa0, 0x202f) + ']', 'g');

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(SPACES, ' ').replace(/\s+/g, ' ');
}

async function render<T>(component: Type<T>, data: Partial<Record<keyof CommunityData, unknown>>) {
  TestBed.configureTestingModule({
    providers: [...provideAccountTesting(), { provide: CommunityData, useValue: data }],
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(component);
  if (component !== (SiteBanner as Type<unknown>)) {
    fixture.componentRef.setInput('language', 'fr');
  }
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
  return { fixture, root: fixture.nativeElement as HTMLElement };
}

describe('Page « Partenaires » (plan L8, N5)', () => {
  it('niveaux dans l’ordre, logo, présentation, site sûr ; sans niveau à la fin', async () => {
    const { root } = await render(SponsorsOverview, {
      sponsors: vi.fn().mockResolvedValue({
        levels: [
          {
            name_fr: 'Or',
            name_en: 'Gold',
            logo_size: 'large',
            sponsors: [
              {
                name: 'Banque du Golfe',
                website: 'https://banque.example',
                description_fr: 'Banque régionale',
                description_en: 'Regional bank',
                logo_url: '/api/v1/public/files/abc/logo.png',
                logo_width: 300,
                logo_height: 120,
              },
              {
                name: 'Piège',
                website: 'javascript:alert(1)',
                description_fr: '',
                description_en: '',
                logo_url: '',
                logo_width: null,
                logo_height: null,
              },
            ],
          },
        ],
        others: [
          {
            name: 'Mairie',
            website: '',
            description_fr: '',
            description_en: '',
            logo_url: '',
            logo_width: null,
            logo_height: null,
          },
        ],
      }),
    });
    const headings = Array.from(root.querySelectorAll('h2')).map((item) =>
      item.textContent!.trim(),
    );
    expect(headings).toEqual(['Or', 'Avec le soutien de']);
    expect(root.querySelector('ul.cards.large')).not.toBeNull();
    expect(root.querySelector('img[alt="Logo de Banque du Golfe"]')!.getAttribute('src')).toBe(
      '/api/v1/public/files/abc/logo.png',
    );
    expect(text(root)).toContain('Banque régionale');
    const links = Array.from(root.querySelectorAll('a')).map((item) => item.getAttribute('href'));
    expect(links).toEqual(['https://banque.example']);
  });

  it('aucun partenaire publié : la page l’annonce', async () => {
    const { root } = await render(SponsorsOverview, {
      sponsors: vi.fn().mockRejectedValue(new GcApiError(404, 'not_found', 'Introuvable.')),
    });
    expect(text(root)).toContain('Les partenaires de la conférence seront présentés ici.');
  });
});

describe('Page « Intervenants » (plan L8, N6)', () => {
  it('biographie, photo, passages à l’heure de la conférence reliés à la session', async () => {
    const { root } = await render(SpeakersOverview, {
      speakers: vi.fn().mockResolvedValue({
        timezone: 'Africa/Abidjan',
        speakers: [
          {
            name: 'Ama Owusu',
            institution: 'Université de Ghana',
            bio: 'Biologiste.',
            photo_url: '/api/v1/public/files/p/ama.jpg',
            talks: [
              {
                session_id: 21,
                session_title_fr: 'Plénière',
                session_title_en: 'Plenary',
                title_fr: 'Conférence invitée',
                title_en: '',
                starts_at: '2027-06-01T11:00:00Z',
                ends_at: '2027-06-01T12:00:00Z',
                room: 'Amphi A',
              },
            ],
          },
        ],
      }),
    });
    expect(text(root)).toContain('Ama Owusu');
    expect(text(root)).toContain('Biologiste.');
    expect(text(root)).toContain('11:00');
    expect(text(root)).toContain('Amphi A');
    expect(root.querySelector('a[href="/fr/programme/session/21"]')!.textContent).toContain(
      'Conférence invitée',
    );
    expect(root.querySelector('img')!.getAttribute('alt')).toBe('');
  });

  it('programme non publié (404) : la page l’annonce', async () => {
    const { root } = await render(SpeakersOverview, {
      speakers: vi.fn().mockRejectedValue(new GcApiError(404, 'not_found', 'Introuvable.')),
    });
    expect(text(root)).toContain('seront présentés ici avec le programme');
  });
});

describe('Page « Actualités » (plan L8, N10)', () => {
  it('actualités ancrées, texte assaini au rendu', async () => {
    const { root } = await render(NewsOverview, {
      news: vi.fn().mockResolvedValue([
        {
          id: 4,
          title_fr: 'Changement de salle',
          title_en: 'Room change',
          body_fr: '<p>Salle A.</p><script>alert(1)</script><img src=x onerror=alert(1)>',
          body_en: '',
          published_at: '2027-05-02T08:00:00Z',
        },
      ]),
    });
    const article = root.querySelector('article#actualite-4')!;
    expect(article.querySelector('h2')!.textContent).toContain('Changement de salle');
    expect(article.innerHTML).not.toContain('<script');
    expect(article.innerHTML).not.toContain('onerror');
    expect(text(root)).toContain('Salle A.');
  });
});

describe('Bandeau de dernière minute (plan L8, N10)', () => {
  beforeEach(() => sessionStorage.clear());

  it('annoncé, lien vers l’actualité, refermé pour la visite', async () => {
    const banner = vi.fn().mockResolvedValue({
      banner: {
        id: 4,
        title_fr: 'Changement de salle',
        title_en: 'Room change',
        message_fr: 'La plénière a lieu en salle A.',
        message_en: '',
        news: true,
      },
    });
    const { fixture, root } = await render(SiteBanner, { banner });
    const status = root.querySelector('[role="status"]')!;
    expect(text(status as HTMLElement)).toContain(
      'Changement de salle — La plénière a lieu en salle A.',
    );
    expect(root.querySelector('a')!.getAttribute('href')).toBe('/fr/actualites#actualite-4');
    root.querySelector('button')!.click();
    fixture.detectChanges();
    expect(root.querySelector('[role="status"]')).toBeNull();
    expect(sessionStorage.getItem('gc-banner-dismissed')).toBe('4');
  });

  it('aucun bandeau ou erreur : rien n’est affiché', async () => {
    const { root } = await render(SiteBanner, {
      banner: vi.fn().mockRejectedValue(new Error('réseau')),
    });
    expect(root.querySelector('[role="status"]')).toBeNull();
  });
});
