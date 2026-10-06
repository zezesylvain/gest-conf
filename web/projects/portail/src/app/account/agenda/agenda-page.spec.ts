import { TestBed } from '@angular/core/testing';
import { AgendaEntry, Api } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { AgendaPage, dayInZone, groupByDay } from './agenda-page';

function entry(overrides: Partial<AgendaEntry> = {}): AgendaEntry {
  return {
    edition: { code: 'GC27', title_fr: 'GEST-CONF 2027', title_en: '', timezone: 'Europe/Paris' },
    version: 2,
    role: 'presenter',
    session: { id: 10, kind: 'parallel', title_fr: 'Santé numérique', title_en: 'Digital health' },
    slot: 1,
    starts_at: '2027-06-01T07:00:00Z',
    ends_at: '2027-06-01T07:20:00Z',
    duration_min: 20,
    room: { name: 'Amphi A', is_accessible: true, access_note: 'Bâtiment B' },
    title: 'Étude sur le paludisme',
    title_en: '',
    reference: 'GC27-0001',
    co_speakers: ['Mariam Traoré'],
    chairs: ['Koffi Yao'],
    instructions: 'Clé USB à 8 h 45.',
    ...overrides,
  };
}

describe('« Mon passage » (plan L5, I8)', () => {
  it('jour dans le fuseau de l’édition ; regroupement par édition et par jour', () => {
    expect(dayInZone('2027-05-31T23:30:00Z', 'Europe/Paris')).toBe('2027-06-01');
    const groups = groupByDay([
      entry({ starts_at: '2027-06-02T07:00:00Z', ends_at: '2027-06-02T08:00:00Z', role: 'chair' }),
      entry(),
    ]);
    expect(groups.map((group) => group.day)).toEqual(['2027-06-01', '2027-06-02']);
  });

  async function render(entries: AgendaEntry[]) {
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: Api, useValue: { invoke: vi.fn().mockResolvedValue(entries) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(AgendaPage);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('passage : heure de l’édition, rôle, salle et accès, co-intervenants, consignes, .ics', async () => {
    const root = await render([entry()]);
    const text = root.textContent ?? '';
    expect(text).toContain('mardi 1 juin 2027');
    expect(text).toContain('Europe/Paris');
    expect(text).toContain('09:00 –');
    expect(text).toContain('09:20');
    expect(text).toContain('Présentation');
    expect(text).toContain('Étude sur le paludisme');
    expect(text).toContain('Amphi A');
    expect(text).toContain('Bâtiment B');
    expect(text).toContain('Avec : Mariam Traoré');
    expect(text).toContain('Présidence : Koffi Yao');
    expect(text).toContain('Clé USB à 8 h 45.');
    const ics = root.querySelector('a[download]')!;
    expect(ics.getAttribute('href')).toBe('/api/v1/me/agenda.ics');
  });

  it('aucun passage publié : message, pas de lien .ics', async () => {
    const root = await render([]);
    expect(root.textContent).toContain('Aucun passage au programme publié');
    expect(root.querySelector('a[download]')).toBeNull();
  });
});
