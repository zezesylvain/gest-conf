import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { MeStore } from '@gestconf/shared';
import { TEST_ME, useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { SubmissionsPage } from './submissions-page';
import { SubmissionsService } from './submissions.service';
import { testEdition, testSubmission } from './testing';

describe('SubmissionsPage', () => {
  let service: Record<string, ReturnType<typeof vi.fn>>;
  let me = { ...TEST_ME, profile_complete: true };

  beforeEach(async () => {
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-06-01T00:00:00Z'));
    service = { list: vi.fn(), currentEdition: vi.fn(), create: vi.fn() };
    me = { ...TEST_ME, profile_complete: true };
    TestBed.configureTestingModule({
      imports: [SubmissionsPage],
      providers: [
        ...provideAccountTesting(),
        { provide: SubmissionsService, useValue: service },
        { provide: MeStore, useValue: { me: () => me } },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  async function render() {
    const fixture = TestBed.createComponent(SubmissionsPage);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('liste : référence ou « Brouillon », état traduit, échéance si modifiable', async () => {
    service['list'].mockResolvedValue([
      testSubmission(),
      testSubmission({
        id: 8,
        reference: 'GC27-0001',
        status: 'submitted',
        title: '',
        can_edit: false,
      }),
    ]);
    service['currentEdition'].mockResolvedValue(testEdition());
    const root = await render();
    const rows = [...root.querySelectorAll('tbody tr')].map((row) => row.textContent ?? '');
    expect(rows[0]).toContain('Brouillon');
    expect(rows[0]).toContain('Réseaux de neurones');
    expect(rows[0]).toContain('2026');
    expect(rows[1]).toContain('GC27-0001');
    expect(rows[1]).toContain('(sans titre)');
    expect(rows[1]).toContain('Soumise');
    expect(rows[1]).toContain('—');
    expect(root.querySelector('a[href="/compte/soumissions/8"]')).not.toBeNull();
  });

  it('appel ouvert : nouveau brouillon puis ouverture de l’assistant', async () => {
    service['list'].mockResolvedValue([]);
    service['currentEdition'].mockResolvedValue(testEdition());
    service['create'].mockResolvedValue(testSubmission({ id: 12 }));
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const root = await render();
    expect(root.textContent).toContain('Vous n’avez encore aucune soumission'.replace('’', "'"));
    const button = root.querySelector<HTMLButtonElement>('button')!;
    expect(button.textContent).toContain('Nouvelle soumission (GC27)');
    button.click();
    await vi.waitFor(() => expect(navigate).toHaveBeenCalledWith(['/compte/soumissions', 12]));
    expect(service['create']).toHaveBeenCalledWith('GC27');
  });

  it('appel fermé : pas de bouton, message (le serveur revérifie, RG-02)', async () => {
    vi.setSystemTime(new Date('2027-01-15T00:00:00Z'));
    service['list'].mockResolvedValue([]);
    service['currentEdition'].mockResolvedValue(testEdition());
    const root = await render();
    expect(root.querySelector('button')).toBeNull();
    expect(root.textContent).toContain("n'est pas ouvert");
  });

  it('profil incomplet : lien vers le profil, bouton désactivé', async () => {
    me = { ...TEST_ME, profile_complete: false };
    service['list'].mockResolvedValue([]);
    service['currentEdition'].mockResolvedValue(testEdition());
    const root = await render();
    expect(root.querySelector('a[href="/compte/profil"]')).not.toBeNull();
    expect(root.querySelector<HTMLButtonElement>('button')!.disabled).toBe(true);
  });
});
