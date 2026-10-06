import { DOCUMENT, Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { GcApiError } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../../account/testing';
import { PortalData } from '../portal-data';
import { PageContext } from '../public-portal';
import { ProgramData } from './program-data';
import { ProgramDayPage } from './program-day-page';
import { ProgramOverview } from './program-overview';
import { ProgramSessionPage } from './program-session-page';
import {
  dayPath,
  filterDays,
  filterSessions,
  NO_FILTERS,
  programPath,
  roomColumns,
  sessionPath,
  timeIn,
} from './program-support';
import { DAY, PROGRAM, PROGRAM_SITE, SESSION } from './testing';

describe('Programme public : outils (plan L5, I7)', () => {
  it('adresses FR et EN, avec barre finale', () => {
    expect(programPath('fr')).toBe('/fr/programme/');
    expect(dayPath('2027-06-01', 'en')).toBe('/en/program/2027-06-01/');
    expect(sessionPath(10, 'fr')).toBe('/fr/programme/session/10/');
  });

  it('I12 : heure dans le fuseau de l’édition, pas celui du navigateur', () => {
    expect(timeIn('2027-06-01T07:30:00Z', 'Europe/Paris', 'fr')).toBe('09:30');
    expect(timeIn('2027-06-01T07:30:00Z', 'Africa/Abidjan', 'en')).toBe('07:30');
  });

  it('filtres de l’accueil : jour, salle, thématique, type, texte sans accents', () => {
    expect(filterDays(PROGRAM.days, NO_FILTERS).map((day) => day.sessions.length)).toEqual([2, 1]);
    expect(filterDays(PROGRAM.days, { ...NO_FILTERS, day: '2027-06-02' })).toHaveLength(1);
    const room = filterDays(PROGRAM.days, { ...NO_FILTERS, room: 'Amphi A' });
    expect(room.flatMap((day) => day.sessions.map((s) => s.id))).toEqual([10]);
    expect(filterDays(PROGRAM.days, { ...NO_FILTERS, kind: 'keynote' })[0].date).toBe('2027-06-02');
    const query = filterDays(PROGRAM.days, { ...NO_FILTERS, query: 'SANTE' });
    expect(query.flatMap((day) => day.sessions.map((s) => s.id))).toEqual([10]);
  });

  it('recherche d’un jour : auteurs, intervenants invités, références', () => {
    expect(filterSessions(DAY.sessions, { ...NO_FILTERS, query: 'traore' })).toEqual([SESSION]);
    expect(filterSessions(DAY.sessions, { ...NO_FILTERS, query: 'fatou' })).toEqual([SESSION]);
    expect(filterSessions(DAY.sessions, { ...NO_FILTERS, query: 'gc27-0001' })).toEqual([SESSION]);
    expect(filterSessions(DAY.sessions, { ...NO_FILTERS, query: 'café' })).toHaveLength(1);
  });

  it('grille par salle : une colonne par salle, puis hors salle', () => {
    const columns = roomColumns(DAY.sessions);
    expect(columns.map((column) => column.room)).toEqual(['Amphi A', null]);
  });
});

describe('Programme public : pages', () => {
  let program: Record<string, ReturnType<typeof vi.fn>>;

  async function render<T>(
    component: Type<T>,
    data: Record<string, unknown> = { lang: 'fr' },
    params: Record<string, string> = {},
    lang: 'fr' | 'en' = 'fr',
  ) {
    program = {
      summary: vi.fn().mockResolvedValue(PROGRAM),
      day: vi.fn().mockResolvedValue(DAY),
      session: vi.fn().mockResolvedValue(SESSION),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: ProgramData, useValue: program },
        { provide: PortalData, useValue: { site: vi.fn().mockResolvedValue(PROGRAM_SITE) } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { data, paramMap: convertToParamMap(params) } },
        },
      ],
    });
    await useTestLanguage(lang);
    const fixture = TestBed.createComponent(component);
    return fixture;
  }

  async function settle<T>(fixture: { whenStable(): Promise<unknown>; detectChanges(): void }) {
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture as unknown as T;
  }

  it('accueil : jours et sessions, liens vers les pages du jour et de la session', async () => {
    const fixture = await render(ProgramOverview);
    fixture.componentRef.setInput('language', 'fr');
    fixture.detectChanges();
    await settle(fixture);
    const root = fixture.nativeElement as HTMLElement;
    expect(root.textContent).toContain("Horaires à l'heure locale de la conférence");
    expect(root.querySelector('a[href="/fr/programme/2027-06-01"]')!.textContent).toContain(
      'mardi 1 juin 2027',
    );
    const link = root.querySelector('a[href="/fr/programme/session/10"]')!;
    expect(link.textContent).toContain('Santé numérique');
    expect(root.textContent).toContain('09:00 – 10:00');
    expect(root.textContent).toContain('2 intervention(s)');
    expect(root.textContent).toContain('3 session(s) affichée(s)');
    // Filtre par salle : une seule session.
    const select = Array.from(root.querySelectorAll('select')).find((item) =>
      item.parentElement!.textContent!.includes('Salle'),
    )!;
    select.value = 'Salle B';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    expect(root.textContent).toContain('1 session(s) affichée(s)');
    expect(root.textContent).not.toContain('Santé numérique');
  });

  it('accueil avant publication (404) : « pas encore publié »', async () => {
    const fixture = await render(ProgramOverview);
    program['summary'].mockRejectedValue(new GcApiError(404, 'not_found', ''));
    fixture.componentRef.setInput('language', 'fr');
    fixture.detectChanges();
    await settle(fixture);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      "Le programme n'est pas encore publié.",
    );
  });

  it('jour : liste détaillée (présentatrice signalée), grille par salle, marqueur, langue', async () => {
    const fixture = await render(ProgramDayPage, { lang: 'fr' }, { day: '2027-06-01' });
    fixture.detectChanges();
    await settle(fixture);
    const root = fixture.nativeElement as HTMLElement;
    expect(program['day']).toHaveBeenCalledWith('2027-06-01');
    expect(root.querySelector('article')!.getAttribute('data-gc-rendered')).toBe(
      'fr:program-day-2027-06-01',
    );
    expect(root.querySelector('h1')!.textContent).toContain('mardi 1 juin 2027');
    expect(root.querySelector('.presenter')!.textContent).toContain('Awa Zadi');
    expect(root.textContent).toContain('Président de séance : Koffi Yao');
    expect(root.textContent).toContain('accessible aux personnes à mobilité réduite');
    expect(TestBed.inject(PageContext).paths()).toEqual({
      fr: '/fr/programme/2027-06-01/',
      en: '/en/program/2027-06-01/',
    });
    expect(TestBed.inject(DOCUMENT).title).toBe('Programme — mardi 1 juin 2027 · GEST-CONF 2027');
    const grid = Array.from(root.querySelectorAll('button')).find((item) =>
      item.textContent!.includes('Grille par salle'),
    )!;
    grid.click();
    fixture.detectChanges();
    expect(grid.getAttribute('aria-pressed')).toBe('true');
    expect(
      Array.from(root.querySelectorAll('.column h2')).map((h) => h.textContent!.trim()),
    ).toEqual(['Amphi A', 'Hors salle']);
  });

  it('jour inconnu (404) : page introuvable, sans marqueur', async () => {
    const fixture = await render(ProgramDayPage, { lang: 'fr' }, { day: '2030-01-01' });
    program['day'].mockRejectedValue(new GcApiError(404, 'not_found', ''));
    fixture.detectChanges();
    await settle(fixture);
    const root = fixture.nativeElement as HTMLElement;
    expect(root.querySelector('article')!.hasAttribute('data-gc-rendered')).toBe(false);
    // Le routeur écrit l'adresse sans barre finale ; Apache sert l'adresse canonique.
    expect(root.querySelector('a')!.getAttribute('href')).toBe('/fr/programme');
  });

  it('session (EN) : horaire, salle et accès, intervenant invité avec photo et biographie', async () => {
    const fixture = await render(ProgramSessionPage, { lang: 'en' }, { id: '10' }, 'en');
    fixture.detectChanges();
    await settle(fixture);
    const root = fixture.nativeElement as HTMLElement;
    expect(program['session']).toHaveBeenCalledWith(10);
    expect(root.querySelector('h1')!.textContent).toContain('Digital health');
    expect(root.textContent).toContain('09:00 – 10:00');
    expect(root.textContent).toContain('Bâtiment B');
    expect(root.textContent).toContain('Invited talk');
    expect(root.textContent).toContain('Épidémiologiste.');
    expect(root.querySelector('img')!.getAttribute('src')).toBe('/api/v1/public/files/x/7');
    expect(root.querySelector('a[href="/en/program/2027-06-01"]')).not.toBeNull();
    expect(root.querySelector('article')!.getAttribute('data-gc-rendered')).toBe(
      'en:program-session-10',
    );
  });
});
