import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router } from '@angular/router';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { provideGestionTesting, REVIEWER_EDITION } from '../../../testing/gestion-testing';
import { ReviewsApi } from '../../core/reviews-api';
import { MyReviewsPage } from './my-reviews-page';
import { ReviewFormPage } from './review-form-page';
import { assignmentDetail, assignmentRow, discussion } from './testing';

describe('Espace relecteur (plan L4 §5)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  function setup(detail = assignmentDetail()) {
    api = {
      myAssignments: vi
        .fn()
        .mockResolvedValue([
          assignmentRow(),
          assignmentRow({ id: 13, review_status: 'submitted', can_edit: true }),
          assignmentRow({ id: 14, review_status: 'draft', can_edit: false }),
        ]),
      assignment: vi.fn().mockResolvedValue(detail),
      authors: vi
        .fn()
        .mockResolvedValue([
          { position: 1, first_name: 'Awa', last_name: 'Koné', institution: 'UFHB', country: 'CI' },
        ]),
      discussion: vi.fn().mockResolvedValue(discussion()),
      saveReview: vi.fn().mockResolvedValue({}),
      submitReview: vi.fn().mockResolvedValue({}),
      decline: vi.fn().mockResolvedValue(undefined),
      postReviewerMessage: vi.fn().mockResolvedValue(discussion()),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([REVIEWER_EDITION]),
        { provide: ReviewsApi, useValue: api },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
  }

  async function form(detail = assignmentDetail()) {
    setup(detail);
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(ReviewFormPage);
    fixture.componentRef.setInput('editionId', '3');
    fixture.componentRef.setInput('assignmentId', '12');
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const type = async (code: string, value: string) => {
      const input = root.querySelector<HTMLInputElement>(`#score-${code}`)!;
      input.value = value;
      input.dispatchEvent(new Event('input'));
      await fixture.whenStable();
      fixture.detectChanges();
    };
    return { fixture, root, type };
  }

  it('« Mes évaluations » : échéance et état de chaque évaluation', async () => {
    setup();
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(MyReviewsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    expect(api['myAssignments']).toHaveBeenCalledWith(3);
    const states = Array.from(root.querySelectorAll('tbody .badge')).map((b) => b.textContent!);
    expect(states).toEqual(['à faire', 'envoyée', 'close']);
    expect(root.textContent).toContain('GC27-0001');
  });

  it('RG-04 : soumission anonymisée, PDF par l’endpoint relecteur, aucun auteur', async () => {
    const { root } = await form();
    expect(root.querySelector('h1')!.textContent).toContain('GC27-0001');
    expect(root.querySelector('a[download]')!.getAttribute('href')).toBe(
      '/api/v1/manage/editions/3/reviews/assignments/12/file',
    );
    expect(root.textContent).toContain('Double aveugle');
    expect(api['authors']).not.toHaveBeenCalled();
  });

  it('H4 : note pondérée indicative pendant la saisie, critère facultatif exclu', async () => {
    const { root, type } = await form();
    const score = () => root.querySelector('.score')!.textContent;
    expect(score()).toBe('—');
    for (const [code, value] of [
      ['originalite', '4'],
      ['methode', '4'],
      ['pertinence', '3'],
      ['redaction', '3'],
    ]) {
      await type(code, value);
    }
    // (4×25 + 4×30 + 3×15 + 3×15) / 85 = 3,647… sur 5 → 72,94.
    expect(score()).toBe('72.94');
  });

  it('brouillon puis envoi (RG-06) : la copie complète est transmise', async () => {
    const { fixture, root, type } = await form();
    await type('originalite', '4');
    root.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    expect(api['saveReview']).toHaveBeenCalledWith(
      3,
      12,
      expect.objectContaining({
        scores: {
          originalite: '4',
          methode: null,
          pertinence: null,
          redaction: null,
          impact: null,
        },
      }),
    );
    expect(root.textContent).toContain('Brouillon enregistré.');
    const send = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      b.textContent!.includes('Envoyer l’évaluation'.replace('’', "'")),
    )!;
    send.click();
    await fixture.whenStable();
    expect(api['submitReview']).toHaveBeenCalled();
  });

  it('RG-08 et H11 : discussion sous pseudonymes', async () => {
    const detail = assignmentDetail({
      discussion_open: true,
      review_status: 'submitted',
      review: {
        status: 'submitted',
        version: 1,
        scores: { originalite: '4.0' },
        suggested_type: null,
        submitted_at: '2027-04-20T10:00:00Z',
        weighted_score: '66.00',
      },
    });
    const { root } = await form(detail);
    const titles = Array.from(root.querySelectorAll('.peer h3')).map((h) => h.textContent);
    expect(titles).toEqual(['Relecteur 1', 'Vous']);
    expect(root.textContent).toContain('Président du comité');
    expect(root.textContent).toContain('Renvoyer l');
    // Envoyée : plus de brouillon ni de refus.
    expect(root.textContent).not.toContain('Enregistrer le brouillon');
    expect(root.textContent).not.toContain('Décliner l');
  });

  it('lecture seule après la décision ; sans double aveugle, auteurs affichés', async () => {
    const { root } = await form(assignmentDetail({ can_edit: false, double_blind: false }));
    expect(root.textContent).toContain('n’est plus modifiable'.replace('’', "'"));
    expect(root.querySelector<HTMLInputElement>('#score-methode')!.disabled).toBe(true);
    expect(api['authors']).toHaveBeenCalledWith(3, 12);
    expect(root.textContent).toContain('Awa Koné');
  });

  it('refus motivé avec conflit (H8), puis retour à la liste', async () => {
    const { fixture, root } = await form();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const page = fixture.componentInstance as unknown as {
      declining: { set(v: boolean): void };
      declineForm: { setValue(v: object): void };
      decline(): Promise<void>;
    };
    page.declining.set(true);
    page.declineForm.setValue({ reason: 'Co-auteur récent', conflict: true });
    await page.decline();
    expect(api['decline']).toHaveBeenCalledWith(3, 12, {
      reason: 'Co-auteur récent',
      conflict: true,
    });
    expect(navigate).toHaveBeenCalledWith(['/editions', '3', 'evaluations']);
    expect(root).toBeTruthy();
  });
});
