import { mergeDeep, TranslateLoader, TranslationObject } from '@ngx-translate/core';
import { from, map, Observable } from 'rxjs';

import { AppLanguage, DEFAULT_LANGUAGE, isAppLanguage } from './languages';

export type TranslationImporter = () => Promise<{ default: TranslationObject }>;
export type TranslationImporters = Record<AppLanguage, TranslationImporter>;

/**
 * Charge les fichiers de traduction par import dynamique (un fichier par langue,
 * intégré au build). Contrairement à un chargement HTTP, cela fonctionne aussi
 * pendant le pré-rendu statique du portail.
 */
export class JsonImportLoader extends TranslateLoader {
  constructor(private readonly sources: readonly TranslationImporters[]) {
    super();
  }

  override getTranslation(lang: string): Observable<TranslationObject> {
    const language = isAppLanguage(lang) ? lang : DEFAULT_LANGUAGE;
    return from(Promise.all(this.sources.map((source) => source[language]()))).pipe(
      map((modules) =>
        modules.reduce<TranslationObject>(
          (merged, module) => mergeDeep(merged, module.default),
          {},
        ),
      ),
    );
  }
}
