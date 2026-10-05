import { TestBed } from '@angular/core/testing';
import { GcApiError } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { TranslateService } from '@ngx-translate/core';

import { provideGestionTesting } from '../../testing/gestion-testing';
import { errorMessages } from './page-support';

describe('errorMessages', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: provideGestionTesting() });
    await useTestLanguage('fr');
  });

  it('conflit 409 : message du serveur (ce qui bloque)', () => {
    const translate = TestBed.inject(TranslateService);
    const error = new GcApiError(409, 'in_use', 'Fichier utilisé (affiche de l’édition).');
    expect(errorMessages(translate, error)).toEqual(['Fichier utilisé (affiche de l’édition).']);
  });

  it('erreurs de champ sans formulaire : message général puis messages des champs', () => {
    const translate = TestBed.inject(TranslateService);
    const error = new GcApiError(400, 'validation_error', 'Données invalides.', {
      non_field_errors: ['Section posée sur : home.'],
    });
    expect(errorMessages(translate, error).at(-1)).toBe('Section posée sur : home.');
  });
});
