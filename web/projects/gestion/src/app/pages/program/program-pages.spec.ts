import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { GcApiError, MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import {
  CHAIR_EDITION,
  PROGRAM_EDITION,
  provideGestionTesting,
} from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { ProgramApi } from '../../core/program-api';
import { ProgramSettingsPage } from '../settings/program-settings-page';
import { PersonPicker } from './person-picker';
import { PublicationPage } from './publication-page';
import { RoomsPage } from './rooms-page';
import { SessionsPage } from './sessions-page';
import { board, session } from './testing';

describe('Écrans du programme (plan L5 §5)', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;
  let dialog: ReturnType<typeof vi.fn>;

  async function render<T>(component: Type<T>, edition: MeEdition = PROGRAM_EDITION) {
    api = {
      board: vi.fn().mockResolvedValue(board()),
      createRoom: vi.fn().mockResolvedValue(board({ revision: 8 })),
      updateRoom: vi.fn().mockResolvedValue(board({ revision: 8 })),
      deleteRoom: vi.fn(),
      createSession: vi.fn(),
      updateSession: vi.fn().mockResolvedValue(board({ revision: 8 })),
      deleteSession: vi.fn().mockResolvedValue(board({ revision: 8 })),
      addRole: vi.fn().mockResolvedValue(board({ revision: 8 })),
      removeRole: vi.fn().mockResolvedValue(board({ revision: 8 })),
      createSlot: vi.fn().mockResolvedValue(board({ revision: 8 })),
      deleteSlot: vi.fn().mockResolvedValue(board({ revision: 8 })),
      people: vi.fn().mockResolvedValue([]),
      publish: vi.fn().mockResolvedValue(board({ revision: 7, published_revision: 7 })),
      publications: vi.fn().mockResolvedValue([
        {
          version: 2,
          published_at: '2027-05-20T10:00:00Z',
          published_by: 'Yao Kouassi',
          summary: {
            sessions: { added: 3, changed: 1, removed: 0 },
            people: { added: 4, changed: 1, removed: 1 },
          },
        },
      ]),
      settings: vi
        .fn()
        .mockResolvedValue({ session_buffer_minutes: 5, presenter_registration_required: false }),
      updateSettings: vi.fn().mockResolvedValue({}),
    };
    dialog = vi.fn(() => ({ afterClosed: () => of(true) }));
    TestBed.configureTestingModule({
      providers: [
        ...provideGestionTesting([edition]),
        { provide: ProgramApi, useValue: api },
        { provide: EditionApi, useValue: { tracks: vi.fn().mockResolvedValue([]) } },
        { provide: MatDialog, useValue: { open: dialog } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(component);
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

  describe('Salles (I9)', () => {
    it('création : équipements en liste fermée, capacité vide → null, révision en If-Match', async () => {
      const { fixture, root } = await render(RoomsPage);
      expect(root.textContent).toContain('Vidéoprojecteur');
      button(root, 'Ajouter une salle').click();
      fixture.detectChanges();
      const page = fixture.componentInstance as unknown as {
        form: { patchValue(v: object): void };
        toggleEquipment(item: string, checked: boolean): void;
        save(): Promise<void>;
      };
      page.form.patchValue({ name: 'Salle C' });
      page.toggleEquipment('microphone', true);
      await page.save();
      expect(api['createRoom']).toHaveBeenCalledWith(3, 7, {
        name: 'Salle C',
        capacity: null,
        equipment: ['microphone'],
        note: '',
        is_accessible: false,
        access_note: '',
        is_active: true,
        position: 2,
      });
    });

    it('salle utilisée : 409 in_use, message du serveur ; désactiver à la place', async () => {
      const { fixture, root } = await render(RoomsPage);
      api['deleteRoom'].mockRejectedValue(
        new GcApiError(409, 'in_use', 'Salle utilisée par une session : désactivez-la.'),
      );
      button(root, 'Supprimer').click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(root.textContent).toContain('Salle utilisée par une session : désactivez-la.');
      button(root, 'Désactiver').click();
      await fixture.whenStable();
      expect(api['updateRoom']).toHaveBeenCalledWith(3, 7, 1, { is_active: false });
    });

    it('lecture seule sans program.write', async () => {
      const { root } = await render(RoomsPage, CHAIR_EDITION);
      expect(root.textContent).toContain('Lecture seule');
      expect(root.textContent).not.toContain('Ajouter une salle');
    });
  });

  describe('Sessions (I2, I10, I11, I12)', () => {
    it('sessions groupées par jour, horaires à l’heure de l’édition, conflits signalés', async () => {
      const { root } = await render(SessionsPage);
      const text = root.textContent ?? '';
      expect(text).toContain('mardi 1 juin 2027');
      expect(text).toContain('09:00 – 10:30');
      expect(text).toContain('Pause');
      expect(text).toContain('Président de séance : Awa Zadi');
      expect(text).toContain('1 conflit(s)');
    });

    it('I12 : erreur de conversion renvoyée sur le champ « début »', async () => {
      const { fixture, root } = await render(SessionsPage);
      api['createSession'].mockRejectedValue(
        new GcApiError(400, 'validation_error', 'Données invalides.', {
          starts_local: ['Heure inexistante dans le fuseau de l’édition.'],
        }),
      );
      button(root, 'Ajouter une session').click();
      fixture.detectChanges();
      const page = fixture.componentInstance as unknown as {
        form: { patchValue(v: object): void; controls: Record<string, { errors: unknown }> };
        save(): Promise<void>;
      };
      page.form.patchValue({ title_fr: 'Ouverture', kind: 'opening' });
      await page.save();
      expect(api['createSession']).toHaveBeenCalledWith(
        3,
        7,
        expect.objectContaining({
          title_fr: 'Ouverture',
          starts_local: '2027-06-01T09:00',
          ends_local: '2027-06-01T10:30',
          room: null,
          track: null,
        }),
      );
      expect(page.form.controls['starts_local'].errors).toEqual({
        server: ['Heure inexistante dans le fuseau de l’édition.'],
      });
    });

    it('création : la session reste ouverte pour ses rôles ; ajout d’un président de séance', async () => {
      const { fixture } = await render(SessionsPage);
      const created = board({ revision: 8, sessions: [...board().sessions, session(99)] });
      api['createSession'].mockResolvedValue(created);
      const page = fixture.componentInstance as unknown as {
        startCreate(): void;
        form: { patchValue(v: object): void };
        save(): Promise<void>;
        editing(): number | null;
        rolePerson: { set(v: object): void };
        addRole(s: object): Promise<void>;
      };
      page.startCreate();
      page.form.patchValue({ title_fr: 'Session 99' });
      await page.save();
      expect(page.editing()).toBe(99);
      page.rolePerson.set({
        id: 41,
        name: 'Kofi Mensah',
        institution: '',
        roles: ['SESSION_CHAIR'],
      });
      await page.addRole(session(99));
      expect(api['addRole']).toHaveBeenCalledWith(3, 8, 99, { user: 41, role: 'chair' });
    });

    it('suppression confirmée, avec le nombre de communications rendues à la liste', async () => {
      const { fixture, root } = await render(SessionsPage);
      button(root, 'Supprimer').click();
      await fixture.whenStable();
      const data = dialog.mock.calls[0][1].data;
      expect(data.message).toContain('2 communication(s) retourneront');
      expect(api['deleteSession']).toHaveBeenCalledWith(3, 7, 10);
    });
  });

  describe('Choix d’une personne (I10, I11)', () => {
    it('recherche dans l’édition, nom et institution seulement, choix émis puis annulé', async () => {
      TestBed.configureTestingModule({
        providers: [
          ...provideGestionTesting([PROGRAM_EDITION]),
          {
            provide: ProgramApi,
            useValue: {
              people: vi
                .fn()
                .mockResolvedValue([
                  { id: 41, name: 'Fatou Sow', institution: 'UCAD', roles: ['SPEAKER'] },
                ]),
            },
          },
        ],
      });
      await useTestLanguage('fr');
      const fixture = TestBed.createComponent(PersonPicker);
      fixture.componentRef.setInput('editionId', 3);
      const picked: unknown[] = [];
      fixture.componentInstance.picked.subscribe((value) => picked.push(value));
      fixture.detectChanges();
      await fixture.componentInstance.run('Sow');
      fixture.detectChanges();
      const root = fixture.nativeElement as HTMLElement;
      expect(TestBed.inject(ProgramApi).people).toHaveBeenCalledWith(3, 'Sow');
      button(root, 'Fatou Sow').click();
      fixture.detectChanges();
      expect(picked).toEqual([
        { id: 41, name: 'Fatou Sow', institution: 'UCAD', roles: ['SPEAKER'] },
      ]);
      expect(root.textContent).toContain('Choix : Fatou Sow');
      button(root, 'Changer').click();
      expect(picked.at(-1)).toBeNull();
    });
  });

  describe('Publication (I6, I13, RG-17)', () => {
    it('conflits restants : publication impossible, lien vers le planificateur', async () => {
      const { root } = await render(PublicationPage, CHAIR_EDITION);
      expect(root.textContent).toContain('1 conflit(s)');
      expect(button(root, 'Publier le programme').disabled).toBe(true);
      expect(root.textContent).toContain('Corriger dans le planificateur');
      expect(root.textContent).toContain(
        'Sessions : 3 ajoutée(s), 1 modifiée(s), 0 supprimée(s) ; 6 personne(s) prévenue(s).',
      );
    });

    it('Chair : publication confirmée, révision en If-Match, historique rechargé', async () => {
      const { fixture, root } = await render(PublicationPage, CHAIR_EDITION);
      api['board'].mockResolvedValue(board({ conflicts: [] }));
      const page = fixture.componentInstance as unknown as { reload(): Promise<void> };
      await page.reload();
      fixture.detectChanges();
      button(root, 'Publier le programme').click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(dialog.mock.calls[0][1].data.message).toContain('La version 3 sera publiée.');
      expect(api['publish']).toHaveBeenCalledWith(3, 7);
      expect(api['publications']).toHaveBeenCalledTimes(2);
      expect(root.textContent).toContain('Programme publié (version 3).');
    });

    it('CO programme : pas de bouton de publication (Chair seul)', async () => {
      const { root } = await render(PublicationPage);
      expect(root.textContent).toContain('Seul le président de la conférence publie');
      expect(root.textContent).not.toContain('Publier le programme');
    });
  });

  describe('Paramétrage › Programme (I17)', () => {
    it('tampon (RG-13) et RG-11 enregistrés', async () => {
      const { fixture, root } = await render(ProgramSettingsPage);
      const page = fixture.componentInstance as unknown as {
        form: { patchValue(v: object): void };
      };
      page.form.patchValue({ session_buffer_minutes: 10 });
      button(root, 'Enregistrer').click();
      await fixture.whenStable();
      fixture.detectChanges();
      expect(api['updateSettings']).toHaveBeenCalledWith(3, {
        session_buffer_minutes: 10,
        presenter_registration_required: false,
      });
      expect(root.textContent).toContain('Modifications enregistrées.');
    });

    it('lecture seule : formulaire désactivé, sans bouton', async () => {
      const { root } = await render(ProgramSettingsPage, CHAIR_EDITION);
      expect(root.querySelector<HTMLInputElement>('input[type="number"]')!.disabled).toBe(true);
      expect(root.textContent).not.toContain('Enregistrer');
    });
  });
});
