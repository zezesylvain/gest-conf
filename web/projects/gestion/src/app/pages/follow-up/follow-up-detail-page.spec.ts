import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { ReviewsApi } from '../../core/reviews-api';
import { candidates, followUpDetail, submissionReviews } from '../reviews/testing';
import { FollowUpDetailPage } from './follow-up-detail-page';

describe('FollowUpDetailPage (pilotage, plan L4 §5)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render(detail = followUpDetail()) {
    api = {
      submission: vi.fn().mockResolvedValue(detail),
      candidates: vi.fn().mockResolvedValue(candidates()),
      reviews: vi.fn().mockResolvedValue(submissionReviews()),
      screen: vi.fn().mockResolvedValue({ ...detail, status: 'under_review' }),
      assign: vi.fn().mockResolvedValue({}),
      decide: vi.fn().mockResolvedValue(detail),
      openDiscussion: vi
        .fn()
        .mockResolvedValue(submissionReviews({ discussion_opened_at: '2027-05-02T10:00:00Z' })),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([CHAIR_EDITION]),
        { provide: ReviewsApi, useValue: api },
        {
          provide: EditionApi,
          useValue: {
            edition: vi.fn().mockResolvedValue({ timezone: 'Africa/Abidjan' }),
            submissionTypes: vi
              .fn()
              .mockResolvedValue([{ id: 1, code: 'poster', label_fr: 'Poster' }]),
          },
        },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(FollowUpDetailPage);
    fixture.componentRef.setInput('editionId', '3');
    fixture.componentRef.setInput('submissionId', '7');
    // Chargement en plusieurs appels successifs : laisser se résoudre toutes les promesses.
    await new Promise((resolve) => setTimeout(resolve));
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const button = (text: string) =>
      Array.from(root.querySelectorAll<HTMLButtonElement>('button')).filter((b) =>
        b.textContent!.includes(text),
      );
    return { fixture, root, button };
  }

  it('H10 : rejet sans motif refusé avant l’appel ; recevable ouvre l’évaluation', async () => {
    const { fixture, root, button } = await render();
    button('Non recevable')[0].click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api['screen']).not.toHaveBeenCalled();
    expect(root.textContent).toContain('Indiquez le motif du rejet.');
    button('Recevable')[0].click();
    await fixture.whenStable();
    expect(api['screen']).toHaveBeenCalledWith(3, 7, 'admissible', '');
  });

  it('H8 : conflit d’auteur jamais affectable ; même institution exige un motif', async () => {
    const { fixture, root, button } = await render();
    // Paul (institution) et Kofi (auteur) : seul Paul peut être affecté.
    expect(button('Affecter…')).toHaveLength(1);
    expect(root.textContent).toContain('déjà affecté');
    button('Affecter…')[0].click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Conflit d’intérêts levable'.replace('’', "'"));
    const submit = () => button('Affecter')[button('Affecter').length - 1];
    submit().click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api['assign']).not.toHaveBeenCalled();
    const page = fixture.componentInstance as unknown as {
      assignForm: { setValue(v: object): void };
      assign(): Promise<void>;
    };
    page.assignForm.setValue({ due_local: '', override_reason: 'Départements distincts' });
    await page.assign();
    expect(api['assign']).toHaveBeenCalledWith(3, {
      submission: 7,
      reviewer: 51,
      due_local: null,
      override_reason: 'Départements distincts',
    });
  });

  it('H11, H12 : évaluations nominatives, divergence, ouverture de la discussion', async () => {
    const { fixture, root, button } = await render(followUpDetail({ status: 'under_review' }));
    expect(api['reviews']).toHaveBeenCalledWith(3, 7);
    expect(root.textContent).toContain('Rita Relectrice');
    expect(root.textContent).toContain('Confidentiel.');
    expect(root.textContent).toContain('divergence (seuil 30.00)');
    button('Ouvrir la discussion')[0].click();
    await fixture.whenStable();
    expect(api['openDiscussion']).toHaveBeenCalledWith(3, 7);
  });

  it('H16 : décision provisoire sur une soumission évaluée', async () => {
    const { fixture } = await render(followUpDetail({ status: 'reviewed' }));
    const page = fixture.componentInstance as unknown as {
      decisionForm: { setValue(v: object): void };
      decide(): Promise<void>;
    };
    page.decisionForm.setValue({
      outcome: 'accepted_minor',
      assigned_type: 'poster',
      comment_to_authors: 'Raccourcir.',
    });
    await page.decide();
    expect(api['decide']).toHaveBeenCalledWith(3, 7, {
      outcome: 'accepted_minor',
      assigned_type: 'poster',
      comment_to_authors: 'Raccourcir.',
    });
  });
});
