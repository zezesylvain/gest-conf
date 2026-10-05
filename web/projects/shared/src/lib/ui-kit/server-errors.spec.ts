import { TestBed } from '@angular/core/testing';
import { FormControl, FormGroup, Validators } from '@angular/forms';
import { TranslateService } from '@ngx-translate/core';

import { provideI18nTesting, useTestLanguage } from '../../testing';
import { GcApiError, NON_FIELD_ERRORS } from '../http/api-error';
import {
  apiErrorMessage,
  applyAuthErrors,
  applyServerErrors,
  fieldErrorMessage,
  passwordsMatch,
} from './server-errors';

describe('Erreurs de formulaire', () => {
  let translate: TranslateService;

  beforeEach(async () => {
    TestBed.configureTestingModule({ providers: [provideI18nTesting()] });
    await useTestLanguage('fr');
    translate = TestBed.inject(TranslateService);
  });

  function form() {
    return new FormGroup({
      email: new FormControl('', { nonNullable: true, validators: [Validators.required] }),
      password: new FormControl('', { nonNullable: true }),
    });
  }

  it('applyServerErrors pose les erreurs de champ et renvoie les autres', () => {
    const group = form();
    group.controls.email.setValue('awa@univ.ci');
    const unplaced = applyServerErrors(
      group,
      new GcApiError(400, 'validation_error', 'Non', {
        email: ['Adresse refusée.'],
        inconnu: ['Champ hors formulaire.'],
        [NON_FIELD_ERRORS]: ['Erreur globale.'],
      }),
    );
    expect(group.controls.email.errors).toEqual({ server: ['Adresse refusée.'] });
    expect(fieldErrorMessage(translate, group.controls.email)).toBe('Adresse refusée.');
    expect(unplaced).toEqual(['Champ hors formulaire.', 'Erreur globale.']);
  });

  it('applyAuthErrors traduit par code et place par « param »', () => {
    const group = form();
    const unplaced = applyAuthErrors(translate, group, [
      { code: 'email_password_mismatch', message: 'Serveur', param: 'password' },
      { code: 'code_inconnu', message: 'Message du serveur' },
    ]);
    expect(group.controls.password.errors?.['server']).toEqual([
      'Adresse e-mail ou mot de passe incorrect.',
    ]);
    expect(unplaced).toEqual(['Message du serveur']);
  });

  it('messages des validateurs du client', () => {
    const group = form();
    expect(fieldErrorMessage(translate, group.controls.email)).toBe('Ce champ est obligatoire.');
  });

  it('apiErrorMessage : traduction, sinon message du serveur, sinon générique', () => {
    expect(apiErrorMessage(translate, new GcApiError(429, 'throttled', 'x'))).toContain(
      'Trop de demandes',
    );
    expect(apiErrorMessage(translate, new GcApiError(400, 'autre', 'Message serveur'))).toBe(
      'Message serveur',
    );
    expect(apiErrorMessage(translate, 'n’importe quoi')).toBe(
      'Une erreur inattendue s’est produite.'.replace('’', "'"),
    );
  });

  it('passwordsMatch signale la différence sur « confirm »', () => {
    const group = new FormGroup(
      { password: new FormControl('abc'), confirm: new FormControl('abd') },
      { validators: passwordsMatch },
    );
    expect(group.controls.confirm.errors).toEqual({ passwordMismatch: true });
    group.controls.confirm.setValue('abc');
    expect(group.controls.confirm.errors).toBeNull();
  });
});
