import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Grid } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { ReviewsApi } from '../../core/reviews-api';
import { GridsPage } from './grids-page';

function grid(overrides: Partial<Grid> = {}): Grid {
  return {
    id: 1,
    name: 'Grille',
    version: 1,
    submission_type: null,
    scale_min: 0,
    scale_max: 5,
    locked_at: null,
    is_locked: false,
    criteria: [
      { code: 'fond', label_fr: 'Fond', weight: '60.00', is_required: true, position: 0 },
      { code: 'forme', label_fr: 'Forme', weight: '40.00', is_required: true, position: 1 },
    ],
    ...overrides,
  };
}

describe('GridsPage (RG-05)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render(grids: Grid[]) {
    api = {
      grids: vi.fn().mockResolvedValue(grids),
      updateGrid: vi.fn().mockResolvedValue(grids[0]),
      createGrid: vi.fn().mockResolvedValue(grids[0]),
      duplicateGrid: vi.fn().mockResolvedValue(grids[0]),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([CHAIR_EDITION]),
        { provide: ReviewsApi, useValue: api },
        { provide: EditionApi, useValue: { submissionTypes: vi.fn().mockResolvedValue([]) } },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(GridsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const buttons = () => Array.from(root.querySelectorAll<HTMLButtonElement>('button'));
    return { fixture, root, buttons };
  }

  it('RG-05 : somme des poids affichée pendant la saisie, critères transmis', async () => {
    const { fixture, root, buttons } = await render([grid()]);
    buttons()
      .find((b) => b.textContent!.includes('Modifier'))!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Somme des poids : 100');
    const page = fixture.componentInstance as unknown as {
      criteria: { at(i: number): { patchValue(v: object): void } };
      save(): Promise<void>;
    };
    page.criteria.at(1).patchValue({ weight: '30' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Somme des poids : 90');
    await page.save();
    expect(api['updateGrid']).toHaveBeenCalledWith(
      3,
      1,
      expect.objectContaining({
        criteria: [
          expect.objectContaining({ code: 'fond', weight: '60.00' }),
          expect.objectContaining({ code: 'forme', weight: '30' }),
        ],
      }),
    );
  });

  it('grille verrouillée : ni modification ni suppression, duplication seulement', async () => {
    const { buttons, root } = await render([grid({ is_locked: true, locked_at: '2027-04-01' })]);
    const labels = buttons().map((b) => b.textContent!.trim());
    expect(labels).not.toContain('Modifier');
    expect(labels).not.toContain('Supprimer');
    expect(labels).toContain('Dupliquer en nouvelle version');
    expect(root.textContent).toContain('verrouillée');
  });
});
