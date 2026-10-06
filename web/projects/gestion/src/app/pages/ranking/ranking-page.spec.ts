import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Ranking } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { ReviewsApi } from '../../core/reviews-api';
import { RankingPage } from './ranking-page';

function ranking(): Ranking {
  const row = {
    title: 'Étude',
    status: 'reviewed' as const,
    track: 'ia',
    submission_type: 'oral',
    spread: '5.00',
    divergent: false,
    review_count: 2,
    recommendations: { accept: 2 },
    decision: null,
  };
  return {
    simulation: {
      threshold: '70.00',
      accepted: 1,
      total: 3,
      by_type: [{ code: 'oral', total: 3, accepted: 1 }],
      by_track: [{ code: 'ia', total: 3, accepted: 1 }],
    },
    rows: [
      { ...row, id: 1, reference: 'GC27-0001', final_score: '80.00' },
      { ...row, id: 2, reference: 'GC27-0002', final_score: '60.00' },
      {
        ...row,
        id: 3,
        reference: 'GC27-0003',
        final_score: '50.00',
        decision: {
          outcome: 'rejected',
          assigned_type: null,
          comment_to_authors: '',
          decided_by: null,
          decided_at: '2027-05-10T10:00:00Z',
          published_at: null,
        },
      },
    ],
  };
}

describe('RankingPage (US-06, H16, RG-09)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render() {
    api = {
      ranking: vi.fn().mockResolvedValue(ranking()),
      decideBatch: vi.fn().mockResolvedValue({ recorded: 2 }),
      publish: vi.fn().mockResolvedValue({ published: 1 }),
      exportCsv: vi.fn().mockResolvedValue('﻿Référence;Titre\r\n'),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([CHAIR_EDITION]),
        { provide: ReviewsApi, useValue: api },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(RankingPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('simulation : seuil transmis, résultat et décisions préparées selon le seuil', async () => {
    const { fixture, root } = await render();
    const page = fixture.componentInstance as unknown as {
      form: { setValue(v: object): void };
      simulate(): Promise<void>;
      prefill(): void;
      saveBatch(): Promise<void>;
    };
    page.form.setValue({ threshold: '70' });
    await page.simulate();
    fixture.detectChanges();
    expect(api['ranking']).toHaveBeenLastCalledWith(3, { threshold: 70 });
    expect(root.textContent).toContain('1 soumission(s) retenue(s) sur 3');
    page.prefill();
    await page.saveBatch();
    expect(api['decideBatch']).toHaveBeenCalledWith(3, [
      { submission: 1, outcome: 'accepted' },
      { submission: 2, outcome: 'rejected' },
      { submission: 3, outcome: 'rejected' },
    ]);
  });

  it('RG-09 : publication confirmée des décisions provisoires', async () => {
    const { fixture, root } = await render();
    const publish = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
      b.textContent!.includes('Publier les résultats (1)'),
    )!;
    publish.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api['publish']).toHaveBeenCalledWith(3);
    expect(root.textContent).toContain('1 décision(s) publiée(s).');
  });

  it('export CSV lu par le client (réauthentification gérée par l’intercepteur)', async () => {
    const { fixture } = await render();
    const create = vi.fn().mockReturnValue('blob:x');
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const page = fixture.componentInstance as unknown as { exportCsv(): Promise<void> };
    await page.exportCsv();
    expect(api['exportCsv']).toHaveBeenCalledWith(3);
    expect(create).toHaveBeenCalled();
    expect(revoke).toHaveBeenCalledWith('blob:x');
  });
});
