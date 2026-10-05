import { AbstractControl, FormGroup } from '@angular/forms';
import { TranslateService } from '@ngx-translate/core';

import { GcApiError, NON_FIELD_ERRORS } from '../http/api-error';

/** Erreur de validation posée par le serveur sur un champ (clé `server`). */
export interface ServerFieldError {
  server: string[];
}

/**
 * Reporte les erreurs de champ du serveur sur le formulaire (plan L1 §10.1).
 * Les champs inconnus du formulaire et les erreurs globales sont renvoyés pour être
 * affichés dans le résumé d'erreurs. Le premier champ en erreur doit recevoir le focus
 * (fait par le composant, `focusFirstInvalid`).
 */
export function applyServerErrors(form: FormGroup, error: GcApiError): string[] {
  const unplaced: string[] = [];
  for (const [name, messages] of Object.entries(error.fields)) {
    const control: AbstractControl | null =
      name === NON_FIELD_ERRORS ? null : form.get(name === 'password1' ? 'password' : name);
    if (control) {
      control.setErrors({ ...(control.errors ?? {}), server: messages });
      control.markAsTouched();
    } else {
      unplaced.push(...messages);
    }
  }
  return unplaced;
}

/**
 * Message d'une erreur d'API dans la langue courante : traduction de
 * `shared.errors.<code>` si elle existe, sinon message du serveur (déjà traduit par
 * Django ou allauth grâce à `Accept-Language`), sinon message générique.
 */
export function apiErrorMessage(translate: TranslateService, error: unknown): string {
  if (error instanceof GcApiError) {
    return codeMessage(translate, error.code, error.message);
  }
  return translate.instant('shared.errors.unexpected');
}

/** Traduction d'un code d'erreur (`shared.errors.<code>`), sinon message du serveur. */
export function codeMessage(translate: TranslateService, code: string, serverMessage = ''): string {
  const key = `shared.errors.${code}`;
  const translated = translate.instant(key);
  if (translated && translated !== key) {
    return translated;
  }
  return serverMessage || translate.instant('shared.errors.unexpected');
}

/**
 * Erreurs d'une réponse d'allauth (`errors[]` d'un `AuthResult`) : posées sur les champs du
 * formulaire (`param`), les autres renvoyées pour le résumé. Messages traduits par code.
 */
export function applyAuthErrors(
  translate: TranslateService,
  form: FormGroup,
  errors: readonly { code: string; message: string; param?: string }[],
): string[] {
  const unplaced: string[] = [];
  for (const item of errors) {
    const message = codeMessage(translate, item.code, item.message);
    const control = item.param
      ? form.get(item.param === 'password1' ? 'password' : item.param)
      : null;
    if (control) {
      const previous = (control.errors?.['server'] as string[] | undefined) ?? [];
      control.setErrors({ ...(control.errors ?? {}), server: [...previous, message] });
      control.markAsTouched();
    } else {
      unplaced.push(message);
    }
  }
  return unplaced;
}

/** Place le focus sur le premier champ invalide d'un formulaire (accessibilité, §10.5). */
export function focusFirstInvalid(root: HTMLElement): void {
  const target = root.querySelector<HTMLElement>(
    'input.ng-invalid, select.ng-invalid, textarea.ng-invalid, [aria-invalid="true"]',
  );
  target?.focus();
}

/**
 * Message de la première erreur d'un champ, dans la langue courante. Les erreurs
 * `server` (posées par `applyServerErrors`) sont affichées telles quelles.
 */
export function fieldErrorMessage(
  translate: TranslateService,
  control: AbstractControl | null,
): string {
  const errors = control?.errors;
  if (!errors) {
    return '';
  }
  if (errors['server']) {
    return (errors['server'] as string[]).join(' ');
  }
  if (errors['required']) {
    return translate.instant('shared.form.required');
  }
  if (errors['email']) {
    return translate.instant('shared.form.email');
  }
  if (errors['minlength']) {
    return translate.instant('shared.form.minlength', {
      min: errors['minlength'].requiredLength,
    });
  }
  if (errors['maxlength']) {
    return translate.instant('shared.form.maxlength', {
      max: errors['maxlength'].requiredLength,
    });
  }
  if (errors['passwordMismatch']) {
    return translate.instant('shared.form.passwordMismatch');
  }
  return translate.instant('shared.errors.validation_error');
}

/** Validateur de groupe : `password` et `confirm` identiques (erreur posée sur `confirm`). */
export function passwordsMatch(group: AbstractControl): null {
  const password = group.get('password');
  const confirm = group.get('confirm');
  if (!password || !confirm) {
    return null;
  }
  const mismatch = !!confirm.value && password.value !== confirm.value;
  const others = { ...(confirm.errors ?? {}) };
  delete others['passwordMismatch'];
  if (mismatch) {
    confirm.setErrors({ ...others, passwordMismatch: true });
  } else {
    confirm.setErrors(Object.keys(others).length ? others : null);
  }
  return null;
}
