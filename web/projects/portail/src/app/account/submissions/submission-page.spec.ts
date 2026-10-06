import { TestBed } from '@angular/core/testing';
import { RouterTestingHarness } from '@angular/router/testing';
import { GcApiError, Submission } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { SubmissionPage } from './submission-page';
import { SubmissionsService } from './submissions.service';
import { testEdition, testSubmission } from './testing';

describe('SubmissionPage', () => {
  let service: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    service = {
      get: vi.fn().mockResolvedValue(testSubmission()),
      currentEdition: vi.fn().mockResolvedValue(testEdition()),
      check: vi.fn().mockResolvedValue({
        complete: false,
        missing: { file: ['Fichier PDF obligatoire.'] },
        duplicates: [],
      }),
      timeline: vi.fn().mockResolvedValue({ history: [], revisions: [] }),
      update: vi.fn(),
      setAuthors: vi.fn(),
      upload: vi.fn(),
      removeFile: vi.fn(),
      submit: vi.fn(),
      withdraw: vi.fn(),
      remove: vi.fn(),
      fileUrl: vi.fn().mockReturnValue('/api/v1/submissions/7/file/content'),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting([{ path: 'compte/soumissions/:id', component: SubmissionPage }]),
        { provide: SubmissionsService, useValue: service },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => vi.restoreAllMocks());

  async function open() {
    const harness = await RouterTestingHarness.create();
    const page = await harness.navigateByUrl('/compte/soumissions/7', SubmissionPage);
    const root = harness.routeNativeElement as HTMLElement;
    // Chargement asynchrone (soumission, édition, puis vérification et historique).
    await vi.waitFor(() => {
      harness.detectChanges();
      expect(service['timeline']).toHaveBeenCalled();
      expect(root.querySelector('.steps')).not.toBeNull();
    });
    await harness.fixture.whenStable();
    harness.detectChanges();
    const step = async (index: number) => {
      root.querySelectorAll<HTMLButtonElement>('.step')[index].click();
      await harness.fixture.whenStable();
      harness.detectChanges();
    };
    // Méthodes protégées du composant, appelées directement (sans attendre l'anti-rebond).
    const page$ = page as unknown as {
      autosave(): Promise<void>;
      saveAuthors(): Promise<void>;
    };
    return { harness, page: page$, root, step };
  }

  it('identifiant lu dans la route ; informations chargées, résumé compté', async () => {
    const { root } = await open();
    expect(service['get']).toHaveBeenCalledWith(7);
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!.value).toBe(
      'Réseaux de neurones',
    );
    expect(root.textContent).toContain('3 mots (au plus 300)');
    expect(root.textContent).toContain('Brouillon');
  });

  it('sauvegarde automatique : mots-clés découpés, déclarations, If-Match par le service', async () => {
    service['update'].mockImplementation(async (current: Submission) =>
      testSubmission({ revision: current.revision + 1, title: 'Titre modifié' }),
    );
    const { harness, page, root } = await open();
    const title = root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!;
    title.value = 'Titre modifié';
    title.dispatchEvent(new Event('input'));
    const keywords = root.querySelector<HTMLInputElement>('input[formcontrolname=keywords]')!;
    keywords.value = 'IA ; apprentissage,  réseaux ,';
    keywords.dispatchEvent(new Event('input'));
    await page.autosave();
    await harness.fixture.whenStable();
    harness.detectChanges();
    const [current, body] = service['update'].mock.calls[0];
    expect(current.revision).toBe(3);
    expect(body).toMatchObject({
      title: 'Titre modifié',
      keywords: ['IA', 'apprentissage', 'réseaux'],
      track: 'AI',
      submission_type: 'ORAL',
      declarations: { originality: true, ethics: false },
    });
    expect(root.textContent).toContain('Enregistré à');
  });

  it('écritures sérialisées : la seconde part avec la révision rendue par la première', async () => {
    let release!: () => void;
    service['update'].mockImplementation(
      (current: Submission) =>
        new Promise<Submission>((resolve) => {
          release = () => resolve(testSubmission({ revision: current.revision + 1 }));
        }),
    );
    service['setAuthors'].mockImplementation(async (current: Submission) =>
      testSubmission({ revision: current.revision + 1 }),
    );
    const { page, root } = await open();
    const title = root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!;
    title.value = 'Autre';
    title.dispatchEvent(new Event('input'));
    const first = page.autosave();
    const second = page.saveAuthors();
    await Promise.resolve();
    expect(service['setAuthors']).not.toHaveBeenCalled();
    release();
    await Promise.all([first, second]);
    expect(service['setAuthors'].mock.calls[0][0].revision).toBe(4);
  });

  it('auteurs : le bouton enregistre la liste (ordre, correspondant), If-Match par le service', async () => {
    service['setAuthors'].mockImplementation(async (current: Submission) =>
      testSubmission({ revision: current.revision + 1 }),
    );
    const { harness, root, step } = await open();
    await step(1);
    root.querySelector<HTMLButtonElement>('form .actions button[type=submit]')!.click();
    await vi.waitFor(() => expect(service['setAuthors']).toHaveBeenCalled());
    const [current, authors] = service['setAuthors'].mock.calls[0];
    expect(current.revision).toBe(3);
    expect(authors).toEqual([
      expect.objectContaining({ email: 'awa.kone@univ.ci', is_corresponding: true }),
    ]);
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(root.textContent).toContain('Auteurs enregistrés.');
  });

  it('412 : conflit signalé, rechargement sur demande', async () => {
    service['update'].mockRejectedValue(new GcApiError(412, 'stale_revision', 'Périmé.', {}));
    const { harness, page, root } = await open();
    const title = root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!;
    title.value = 'Autre';
    title.dispatchEvent(new Event('input'));
    await page.autosave();
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(root.textContent).toContain('modifiée ailleurs');
    service['get'].mockResolvedValue(testSubmission({ revision: 9, title: 'Version serveur' }));
    [...root.querySelectorAll<HTMLButtonElement>('button')]
      .find((button) => button.textContent?.includes('Recharger'))!
      .click();
    await vi.waitFor(() => expect(service['get']).toHaveBeenCalledTimes(2));
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!.value).toBe(
      'Version serveur',
    );
  });

  it('lecture seule : champs désactivés, aucune action d’écriture', async () => {
    service['get'].mockResolvedValue(
      testSubmission({
        status: 'submitted',
        reference: 'GC27-0001',
        can_edit: false,
        allowed_actions: [],
      }),
    );
    const { harness, page, root, step } = await open();
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname=title]')!.disabled).toBe(
      true,
    );
    expect(root.textContent).toContain('lecture seule');
    expect(root.querySelector('h1')!.textContent).toContain('GC27-0001');
    await page.autosave();
    expect(service['update']).not.toHaveBeenCalled();
    await step(1);
    expect(root.textContent).not.toContain('Ajouter un auteur');
    harness.detectChanges();
  });

  it('fichier : politique du type, avertissement double aveugle, lien authentifié', async () => {
    service['get'].mockResolvedValue(
      testSubmission({
        file: {
          id: 1,
          kind: 'main',
          original_name: 'article.pdf',
          version: 2,
          pages: 8,
          size: 1000,
          metadata_removed: true,
          uploaded_at: '2026-10-01T10:00:00Z',
        },
      }),
    );
    const { root, step } = await open();
    await step(2);
    expect(root.textContent).toContain('Fichier PDF obligatoire, 10 Mo au plus.');
    expect(root.textContent).toContain('double aveugle');
    expect(
      root.querySelector('a[href="/api/v1/submissions/7/file/content"]')!.textContent,
    ).toContain('article.pdf');
    expect(root.textContent).toContain('métadonnées supprimées');
  });

  it('récapitulatif : manques listés, « Soumettre » désactivé tant qu’incomplet (RG-01)', async () => {
    const { root, step } = await open();
    await step(4);
    expect(root.textContent).toContain('Fichier PDF obligatoire.');
    const submit = [...root.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent?.includes('Soumettre'),
    )!;
    expect(submit.disabled).toBe(true);
  });

  it('F15 : doublon possible signalé, soumission toujours possible', async () => {
    service['check'].mockResolvedValue({
      complete: true,
      missing: {},
      duplicates: [{ id: 3, reference: 'GC27-0002', status: 'submitted', title: 'Réseaux' }],
    });
    const { root, step } = await open();
    await step(4);
    expect(root.textContent).toContain('vous avez déjà une soumission au même titre');
    expect(root.textContent).toContain('GC27-0002 — Réseaux (Soumise)');
    const submit = [...root.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
      button.textContent?.includes('Soumettre'),
    )!;
    expect(submit.disabled).toBe(false);
  });

  it('soumission complète : référence annoncée', async () => {
    service['check'].mockResolvedValue({ complete: true, missing: {}, duplicates: [] });
    service['submit'].mockResolvedValue(
      testSubmission({
        status: 'submitted',
        reference: 'GC27-0003',
        can_edit: true,
        allowed_actions: ['withdraw'],
      }),
    );
    const { harness, root, step } = await open();
    await step(4);
    [...root.querySelectorAll<HTMLButtonElement>('button')]
      .find((button) => button.textContent?.includes('Soumettre'))!
      .click();
    await vi.waitFor(() => expect(service['submit']).toHaveBeenCalledWith(7));
    await harness.fixture.whenStable();
    harness.detectChanges();
    expect(root.textContent).toContain('GC27-0003');
    // Déjà soumise : plus d'invitation à soumettre.
    expect(root.textContent).not.toContain('vous pouvez la soumettre');
    expect(root.textContent).toContain('Retirer la soumission');
  });

  it('retrait : motif exigé', async () => {
    service['get'].mockResolvedValue(
      testSubmission({
        status: 'submitted',
        reference: 'GC27-0001',
        allowed_actions: ['withdraw'],
      }),
    );
    service['withdraw'].mockResolvedValue(
      testSubmission({ status: 'withdrawn', can_edit: false, allowed_actions: [] }),
    );
    const { harness, root, step } = await open();
    await step(4);
    const confirm = () =>
      [...root.querySelectorAll<HTMLButtonElement>('button')].find((button) =>
        button.textContent?.includes('Retirer définitivement'),
      )!;
    expect(confirm().disabled).toBe(true);
    const reason = root.querySelector<HTMLTextAreaElement>('.withdraw textarea')!;
    reason.value = 'Conflit de calendrier';
    reason.dispatchEvent(new Event('input'));
    harness.detectChanges();
    confirm().click();
    await vi.waitFor(() =>
      expect(service['withdraw']).toHaveBeenCalledWith(7, 'Conflit de calendrier'),
    );
  });
});
