/*
 * Outils de test partagés (@gestconf/shared/testing) : à n'importer que dans les fichiers *.spec.ts.
 */
import { Provider } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateLoader, provideTranslateService } from '@ngx-translate/core';

import { JsonImportLoader, TranslationImporters } from './lib/i18n/json-import-loader';
import { LanguageService } from './lib/i18n/language.service';
import { AppLanguage, DEFAULT_LANGUAGE } from './lib/i18n/languages';
import { sharedTranslations } from './lib/i18n/provide-i18n';

/** Traductions réelles (communes + application) pour les tests de composants. */
export function provideI18nTesting(appTranslations?: TranslationImporters): Provider[] {
  const sources = appTranslations ? [sharedTranslations, appTranslations] : [sharedTranslations];
  return provideTranslateService({
    loader: provideTranslateLoader(() => new JsonImportLoader(sources)),
    fallbackLang: DEFAULT_LANGUAGE,
  });
}

/** Charge une langue avant de créer le composant testé. */
export async function useTestLanguage(lang: AppLanguage = DEFAULT_LANGUAGE): Promise<void> {
  await TestBed.inject(LanguageService).use(lang, { remember: false });
}
