import { EnvironmentProviders, inject, provideAppInitializer, Provider } from '@angular/core';
import { TitleStrategy } from '@angular/router';
import { provideTranslateLoader, provideTranslateService } from '@ngx-translate/core';

import { JsonImportLoader, TranslationImporters } from './json-import-loader';
import { LanguageService } from './language.service';
import { DEFAULT_LANGUAGE } from './languages';
import { TranslatedTitleStrategy } from './translated-title.strategy';

export const sharedTranslations: TranslationImporters = {
  fr: () => import('./fr.json'),
  en: () => import('./en.json'),
};

/**
 * Internationalisation FR/EN d'une application : traductions communes (clés « shared.* »)
 * et propres à l'application, chargées avant le premier rendu (y compris au pré-rendu).
 */
export function provideI18n(
  appTranslations: TranslationImporters,
): (Provider | EnvironmentProviders)[] {
  return [
    provideTranslateService({
      loader: provideTranslateLoader(
        () => new JsonImportLoader([sharedTranslations, appTranslations]),
      ),
      fallbackLang: DEFAULT_LANGUAGE,
    }),
    provideAppInitializer(() => inject(LanguageService).init()),
    { provide: TitleStrategy, useClass: TranslatedTitleStrategy },
  ];
}
