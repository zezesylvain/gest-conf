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
      finalVersion: vi.fn(),
      confirmPresentation: vi.fn(),
      finalVersionUrl: vi.fn().mockReturnValue('/api/v1/submissions/7/final-version/content'),
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

  describe('après publication des résultats (plan L4, H18)', () => {
    function decided(overrides: Partial<Submission> = {}): Submission {
      return testSubmission({
        status: 'accepted_minor',
        reference: 'GC27-0001',
        can_edit: false,
        allowed_actions: ['final_version'],
        final_deadline: '2099-01-15T23:59:00Z',
        decision: {
          outcome: 'accepted_minor',
          assigned_type: { code: 'POSTER', label_fr: 'Affiche', label_en: 'Poster' },
          comment_to_authors: 'Bravo, quelques corrections.',
          published_at: '2026-10-05T10:00:00Z',
          reviews: [
            { pseudonym_rank: 1, comment: 'Clarifier la méthode.' },
            { pseudonym_rank: 2, comment: 'Ajouter une référence.' },
          ],
        },
        ...overrides,
      });
    }

    function button(root: HTMLElement, label: string): HTMLButtonElement {
      return [...root.querySelectorAll<HTMLButtonElement>('button')].find((item) =>
        item.textContent?.includes(label),
      )!;
    }

    function chooseFile(root: HTMLElement, harness: { detectChanges(): void }): File {
      const file = new File(['%PDF-1.4'], 'final.pdf', { type: 'application/pdf' });
      const input = root.querySelector<HTMLInputElement>('.final input[type=file]')!;
      Object.defineProperty(input, 'files', { value: [file] });
      input.dispatchEvent(new Event('change'));
      harness.detectChanges();
      return file;
    }

    it('RG-10 : décision, format attribué, message du comité, commentaires sous pseudonymes', async () => {
      service['get'].mockResolvedValue(decided());
      const { root } = await open();
      const section = root.querySelector('.decision')!;
      expect(section.textContent).toContain('Décision du comité');
      expect(root.textContent).toContain('Consultez la décision du comité');
      expect(section.textContent).toContain('Acceptée sous réserve de corrections');
      expect(section.textContent).toContain('Format attribué : Affiche');
      expect(section.textContent).toContain('Bravo, quelques corrections.');
      const reviewers = [...section.querySelectorAll('.review h4')].map((h) =>
        h.textContent?.trim(),
      );
      expect(reviewers).toEqual(['Relecteur 1', 'Relecteur 2']);
      expect(section.textContent).toContain('Clarifier la méthode.');
      // Ni note ni recommandation : le serveur ne les sert pas, l'écran n'en prévoit pas.
      expect(section.textContent).not.toMatch(/\/\s*100|note|recommandation/i);
    });

    it('H18 : lettre de réponse exigée pour une acceptation sous réserve, puis dépôt', async () => {
      service['get'].mockResolvedValue(decided());
      service['finalVersion'].mockResolvedValue(
        decided({
          status: 'camera_ready_received',
          final_version: {
            file: {
              id: 31,
              kind: 'camera_ready',
              original_name: 'final.pdf',
              version: 1,
              size: 8,
              pages: 1,
              metadata_removed: false,
              uploaded_at: '2026-10-06T09:00:00Z',
            },
            response_letter: 'Méthode clarifiée.',
            submitted_at: '2026-10-06T09:00:00Z',
          },
        }),
      );
      const { harness, root } = await open();
      expect(root.querySelector('.final')!.textContent).toContain('Obligatoire');
      chooseFile(root, harness);
      button(root, 'Déposer la version finale').click();
      await harness.fixture.whenStable();
      harness.detectChanges();
      expect(service['finalVersion']).not.toHaveBeenCalled();
      const alert = root.querySelector('.final [role=alert]')!.textContent;
      expect(alert).toContain('La lettre de réponse aux relecteurs est obligatoire.');
      expect(alert).not.toContain('trop longue');
      const letter = root.querySelector<HTMLTextAreaElement>('.final textarea')!;
      letter.value = 'Méthode clarifiée.';
      letter.dispatchEvent(new Event('input'));
      harness.detectChanges();
      button(root, 'Déposer la version finale').click();
      await vi.waitFor(() => {
        harness.detectChanges();
        expect(root.textContent).toContain('Version finale déposée.');
      });
      expect(service['finalVersion']).toHaveBeenCalledWith(
        7,
        expect.any(File),
        'Méthode clarifiée.',
      );
      const link = root.querySelector<HTMLAnchorElement>('.final a')!;
      expect(link.getAttribute('href')).toBe('/api/v1/submissions/7/final-version/content');
      expect(root.textContent).toContain('Version finale reçue');
      expect(root.textContent).toContain('Remplacer la version finale');
    });

    it('H18 : date limite passée, plus de formulaire', async () => {
      service['get'].mockResolvedValue(decided({ final_deadline: '2020-01-01T00:00:00Z' }));
      const { root } = await open();
      expect(root.querySelector('.final input[type=file]')).toBeNull();
      expect(root.querySelector('.final')!.textContent).toContain(
        'La date limite de dépôt de la version finale est passée.',
      );
    });

    it('acceptée : lettre facultative ; retrait possible depuis la décision', async () => {
      service['get'].mockResolvedValue(
        decided({
          status: 'accepted',
          allowed_actions: ['withdraw', 'final_version'],
          decision: {
            outcome: 'accepted',
            assigned_type: null,
            comment_to_authors: '',
            published_at: '2026-10-05T10:00:00Z',
            reviews: [],
          },
        }),
      );
      service['finalVersion'].mockResolvedValue(decided({ status: 'camera_ready_received' }));
      const { harness, root } = await open();
      expect(root.querySelector('.final')!.textContent).toContain('Facultative');
      expect(root.querySelector('.decision')!.textContent).toContain(
        'Aucun commentaire des relecteurs.',
      );
      expect(root.querySelector('.decision .withdraw')).not.toBeNull();
      const file = chooseFile(root, harness);
      button(root, 'Déposer la version finale').click();
      await vi.waitFor(() => expect(service['finalVersion']).toHaveBeenCalledWith(7, file, ''));
    });

    it('I5 : confirmation de présentation, présentateurs choisis parmi les auteurs', async () => {
      const coauthor = {
        position: 2,
        first_name: 'Mariam',
        last_name: 'Traoré',
        email: 'mariam@univ.ci',
        institution: 'INP-HB',
        is_presenter: false,
        has_account: false,
      };
      const ready = decided({
        status: 'camera_ready_received',
        allowed_actions: ['final_version', 'withdraw', 'confirm_presentation'],
        authors: [...testSubmission().authors, coauthor],
      });
      service['get'].mockResolvedValue(ready);
      service['confirmPresentation'].mockResolvedValue(
        decided({
          status: 'confirmed',
          allowed_actions: ['withdraw', 'confirm_presentation'],
          authors: ready.authors,
          presentation: { presenters: [2], confirmed_at: '2026-12-02T10:00:00Z' },
        }),
      );
      const { harness, root } = await open();
      const section = root.querySelector<HTMLElement>('.presentation')!;
      expect(section.textContent).toContain('Désignez qui présentera');
      const boxes = section.querySelectorAll<HTMLInputElement>('input[type=checkbox]');
      // L'auteure marquée présentatrice est cochée par défaut ; on choisit la co-autrice.
      expect([...boxes].map((box) => box.checked)).toEqual([true, false]);
      boxes[0].click();
      boxes[1].click();
      harness.detectChanges();
      button(section, 'Confirmer ma présentation').click();
      await vi.waitFor(() => expect(service['confirmPresentation']).toHaveBeenCalledWith(7, [2]));
      await harness.fixture.whenStable();
      harness.detectChanges();
      expect(root.textContent).toContain('Présentation confirmée.');
      expect(root.querySelector('.presentation')!.textContent).toContain(
        'présentateurs : Mariam Traoré',
      );
      expect(button(root, 'Mettre à jour les présentateurs')).toBeTruthy();
    });

    it('programmée : créneau publié, lien « Mon passage », retrait avec motif', async () => {
      service['get'].mockResolvedValue(
        decided({
          status: 'scheduled',
          allowed_actions: ['withdraw', 'confirm_presentation'],
          presentation: { presenters: [1], confirmed_at: '2026-12-02T10:00:00Z' },
          schedule: {
            version: 1,
            session_id: 10,
            session_title_fr: 'Santé numérique',
            session_title_en: 'Digital health',
            room: 'Amphi A',
            starts_at: '2027-06-01T09:00:00Z',
            ends_at: '2027-06-01T09:20:00Z',
          },
        }),
      );
      const { root } = await open();
      const section = root.querySelector<HTMLElement>('.presentation')!;
      expect(section.textContent).toContain('Programmée :');
      expect(section.textContent).toContain('Santé numérique');
      expect(section.textContent).toContain('Amphi A');
      expect(section.textContent).toContain('– 09:20');
      expect(section.querySelector('a[href="/compte/mon-passage"]')).not.toBeNull();
      const withdraw = section.querySelector('.withdraw')!;
      expect(button(withdraw as HTMLElement, 'Retirer définitivement').disabled).toBe(true);
    });

    it('liste d’attente : décision affichée, pas de version finale', async () => {
      service['get'].mockResolvedValue(
        decided({
          status: 'waitlist',
          allowed_actions: [],
          final_deadline: null,
          decision: {
            outcome: 'waitlist',
            assigned_type: null,
            comment_to_authors: '',
            published_at: '2026-10-05T10:00:00Z',
            reviews: [{ pseudonym_rank: 1, comment: 'Intéressant.' }],
          },
        }),
      );
      const { root } = await open();
      expect(root.querySelector('.decision')!.textContent).toContain("Liste d'attente");
      expect(root.textContent).toContain('un e-mail vous préviendra');
      expect(root.querySelector('.final')).toBeNull();
      expect(root.querySelector('.withdraw')).toBeNull();
    });
  });
});
