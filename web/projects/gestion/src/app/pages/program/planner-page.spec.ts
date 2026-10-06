import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { GcApiError } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import {
  CHAIR_EDITION,
  PROGRAM_EDITION,
  provideGestionTesting,
} from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { ProgramApi } from '../../core/program-api';
import { DragItem, DropTarget, PlannerPage } from './planner-page';
import { board } from './testing';

interface Page {
  drop(event: unknown): Promise<void>;
}

describe('PlannerPage (plan L5, I15 ; RG-12, RG-13)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render(edition = PROGRAM_EDITION) {
    api = {
      board: vi.fn().mockResolvedValue(board()),
      createSlot: vi.fn().mockResolvedValue(board({ revision: 8 })),
      updateSlot: vi.fn().mockResolvedValue(board({ revision: 8 })),
      deleteSlot: vi.fn().mockResolvedValue(board({ revision: 8 })),
    };
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([edition]),
        { provide: ProgramApi, useValue: api },
        {
          provide: EditionApi,
          useValue: {
            tracks: vi
              .fn()
              .mockResolvedValue([
                { id: 1, code: 'ia', name_fr: 'Intelligence artificielle', name_en: 'AI' },
              ]),
            submissionTypes: vi
              .fn()
              .mockResolvedValue([{ id: 1, code: 'oral', label_fr: 'Communication orale' }]),
          },
        },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(PlannerPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  function button(root: HTMLElement, text: string): HTMLButtonElement {
    // Libellé exact d'abord (« Placer » n'est pas « Placer dans… »), sinon libellé contenu.
    const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>('button'));
    const found =
      buttons.find((item) => item.textContent!.trim() === text) ??
      buttons.find((item) => item.textContent!.includes(text));
    if (!found) {
      throw new Error(`bouton « ${text} » introuvable`);
    }
    return found;
  }

  async function settle(fixture: { whenStable(): Promise<unknown>; detectChanges(): void }) {
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('grille du jour par salle, liste « à programmer », conflits nommés sans adresse', async () => {
    const { fixture, root } = await render();
    const text = root.textContent ?? '';
    expect(root.querySelectorAll('.column h3')[0].textContent).toContain('Amphi A');
    expect(text).toContain('Hors salle');
    expect(text).toContain('À programmer (2)');
    expect(text).toContain('Modifications non publiées');
    expect(text).toContain(
      'Awa Zadi est attendu(e) à deux endroits en même temps : « Session 10 », « Session 30 » (RG-12).',
    );
    expect(text).toContain('40 / 90 min');
    expect(root.querySelector('#session-card-10')!.classList).toContain('conflict');
    expect(root.querySelector('#slot-1')!.classList).toContain('conflict');
    // Jour suivant : sa seule session ; le conflit reste listé sous la grille.
    const next = button(root, 'mercredi 2 juin 2027');
    expect(next.getAttribute('aria-pressed')).toBe('false');
    next.click();
    fixture.detectChanges();
    expect(next.getAttribute('aria-pressed')).toBe('true');
    expect(root.querySelector('#session-card-40')).not.toBeNull();
    expect(root.querySelector('#session-card-10')).toBeNull();
  });

  it('I15 au clavier : « Placer dans… » puis « Placer », révision en If-Match, annonce', async () => {
    const { fixture, root } = await render();
    const place = button(root, 'Placer dans…');
    expect(place.getAttribute('aria-expanded')).toBe('false');
    place.click();
    await settle(fixture);
    const select = root.querySelector<HTMLSelectElement>('#panel-submission-1 select')!;
    // Pas de pause comme cible : sessions 10, 30 (1er juin) et 40 (2 juin).
    expect(Array.from(select.options).map((option) => option.value)).toEqual(['10', '30', '40']);
    select.value = '30';
    button(root, 'Placer').click();
    await settle(fixture);
    expect(api['createSlot']).toHaveBeenCalledWith(3, 7, 30, { submission: 1 });
    expect(root.querySelector('[role="status"]')!.textContent).toContain(
      '« Étude 1 » placée dans « Session 30 ».',
    );
  });

  it('I15 au clavier : descendre un créneau ; le premier ne monte pas', async () => {
    const { fixture, root } = await render();
    const first = root.querySelector('#slot-1')!;
    expect(first.querySelector<HTMLButtonElement>('button.up')!.disabled).toBe(true);
    first.querySelector<HTMLButtonElement>('button.down')!.click();
    await settle(fixture);
    expect(api['updateSlot']).toHaveBeenCalledWith(3, 7, 1, { session: 10, position: 1 });
  });

  it('I15 : durée et retrait depuis « Actions… »', async () => {
    const { fixture, root } = await render();
    root.querySelector<HTMLButtonElement>('#slot-2 .tools button:last-child')!.click();
    await settle(fixture);
    const panel = root.querySelector('#panel-slot-2')!;
    const duration = panel.querySelector<HTMLInputElement>('input[type="number"]')!;
    duration.value = '25';
    button(panel as HTMLElement, 'Appliquer la durée').click();
    await settle(fixture);
    expect(api['updateSlot']).toHaveBeenCalledWith(3, 7, 2, { duration_min: 25 });
    duration.value = '0';
    button(panel as HTMLElement, 'Appliquer la durée').click();
    await settle(fixture);
    expect(api['updateSlot']).toHaveBeenCalledTimes(1);
    expect(root.textContent).toContain('Durée invalide');
  });

  it('glisser-déposer : placement à la position visée, retour dans la liste', async () => {
    const { fixture } = await render();
    const page = fixture.componentInstance as unknown as Page;
    const data = board();
    const target: DropTarget = { kind: 'session', session: data.sessions[0] };
    const pool: DropTarget = { kind: 'pool' };
    const fromPool: DragItem = { kind: 'submission', submission: data.to_schedule[1] };
    await page.drop({
      item: { data: fromPool },
      container: { data: target },
      previousContainer: { data: pool },
      previousIndex: 1,
      currentIndex: 1,
    });
    expect(api['createSlot']).toHaveBeenCalledWith(3, 7, 10, { submission: 2, position: 1 });
    const placed: DragItem = {
      kind: 'slot',
      slot: data.sessions[0].slots[0],
      session: data.sessions[0],
    };
    await page.drop({
      item: { data: placed },
      container: { data: pool },
      previousContainer: { data: target },
      previousIndex: 0,
      currentIndex: 0,
    });
    expect(api['deleteSlot']).toHaveBeenCalledWith(3, 8, 1);
  });

  it('I14 : révision périmée (412) → brouillon rechargé et message', async () => {
    const { fixture, root } = await render();
    api['createSlot'].mockRejectedValue(
      new GcApiError(412, 'stale_revision', 'Modifié entre-temps.'),
    );
    button(root, 'Placer dans…').click();
    await settle(fixture);
    button(root, 'Placer').click();
    await settle(fixture);
    expect(api['board']).toHaveBeenCalledTimes(2);
    expect(root.textContent).toContain('Le programme a été modifié entre-temps');
  });

  it('lecture seule sans program.write (Chair) : ni « Placer dans… » ni flèches', async () => {
    const { root } = await render(CHAIR_EDITION);
    expect(root.textContent).toContain('Lecture seule');
    expect(root.textContent).not.toContain('Placer dans…');
    expect(root.querySelector('button.down')).toBeNull();
  });
});
