import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { ConfidentialityPage } from './confidentiality-page';
import { GeneralPage } from './general-page';

/** Administrateur : `edition.archive` (indice d'ergonomie ; le serveur vérifie le rôle). */
const ADMIN: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'ADMIN', oc_function: '' }],
  capabilities: [...CHAIR_EDITION.capabilities, 'edition.archive'],
};

const EDITION = {
  id: 3,
  code: 'GC27',
  slug: 'gc27',
  year: 2027,
  title_fr: 'Colloque',
  title_en: 'Conference',
  timezone: 'Africa/Abidjan',
  status: 'published',
  frozen_fields: ['code', 'double_blind'],
  submission_languages: ['fr'],
  published_at: null,
  archived_at: null,
};

describe('RG-19 : réglages gelés après la première soumission', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  async function render<T>(component: Type<T>, edition: MeEdition) {
    api = {
      edition: vi.fn().mockResolvedValue(EDITION),
      updateEdition: vi.fn().mockResolvedValue(EDITION),
      confidentiality: vi.fn().mockResolvedValue({
        double_blind: true,
        reviewers_per_submission: 3,
        frozen_fields: ['code', 'double_blind'],
      }),
      updateConfidentiality: vi.fn().mockResolvedValue({
        double_blind: false,
        reviewers_per_submission: 3,
        frozen_fields: ['code', 'double_blind'],
      }),
    };
    TestBed.configureTestingModule({
      providers: [...provideGestionTesting([edition]), { provide: EditionApi, useValue: api }],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(component);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('président : double aveugle gelé, case désactivée, explication', async () => {
    const { root } = await render(ConfidentialityPage, CHAIR_EDITION);
    expect(root.querySelector<HTMLInputElement>('input[type=checkbox]')!.disabled).toBe(true);
    expect(root.textContent).toContain('Seul un administrateur');
  });

  it('administrateur : changement possible, motif exigé puis transmis', async () => {
    const { fixture, root } = await render(ConfidentialityPage, ADMIN);
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      submit(): Promise<void>;
    };
    page.form.patchValue({ double_blind: false });
    fixture.detectChanges();
    expect(root.textContent).toContain('Motif du changement');
    await page.submit();
    expect(api['updateConfidentiality']).not.toHaveBeenCalled();
    page.form.patchValue({ reason: 'Décision du comité' });
    await page.submit();
    expect(api['updateConfidentiality']).toHaveBeenCalledWith(3, {
      double_blind: false,
      reviewers_per_submission: 3,
      reason: 'Décision du comité',
    });
  });

  it('informations générales : code gelé pour le président, langues des soumissions', async () => {
    const { fixture, root } = await render(GeneralPage, CHAIR_EDITION);
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname=code]')!.disabled).toBe(
      true,
    );
    expect(root.textContent).toContain('Gelé depuis la première soumission');
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(v: object): void };
      submit(): Promise<void>;
    };
    page.form.patchValue({ submission_languages: ['fr', 'en'] });
    await page.submit();
    const body = api['updateEdition'].mock.calls[0][1];
    expect(body.submission_languages).toEqual(['fr', 'en']);
    expect(body.code).toBe('GC27');
    expect('reason' in body).toBe(false); // aucun réglage gelé modifié : pas de motif
  });
});
