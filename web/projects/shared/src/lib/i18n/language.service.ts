import { computed, DOCUMENT, inject, Injectable, PLATFORM_ID } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { AppLanguage, DEFAULT_LANGUAGE, isAppLanguage, SUPPORTED_LANGUAGES } from './languages';

const STORAGE_KEY = 'gestconf.lang';

/** Langue active de l'interface (FR/EN), synchronisée avec l'attribut lang de <html>. */
@Injectable({ providedIn: 'root' })
export class LanguageService {
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));

  readonly languages = SUPPORTED_LANGUAGES;

  readonly current = computed<AppLanguage>(() => {
    const lang = this.translate.currentLang();
    return isAppLanguage(lang) ? lang : DEFAULT_LANGUAGE;
  });

  /**
   * Langue initiale : choix mémorisé, sinon langue du navigateur, sinon français.
   * Le pré-rendu (SSG) se fait toujours dans la langue par défaut.
   */
  init(): Promise<void> {
    return this.use(this.detect(), { remember: false });
  }

  async use(lang: AppLanguage, options = { remember: true }): Promise<void> {
    await firstValueFrom(this.translate.use(lang));
    this.document.documentElement.lang = lang;
    if (options.remember) {
      this.remember(lang);
    }
  }

  private detect(): AppLanguage {
    if (!this.isBrowser) {
      return DEFAULT_LANGUAGE;
    }
    const stored = this.storage()?.getItem(STORAGE_KEY);
    if (isAppLanguage(stored)) {
      return stored;
    }
    const browserLanguage = this.document.defaultView?.navigator.language.slice(0, 2);
    return isAppLanguage(browserLanguage) ? browserLanguage : DEFAULT_LANGUAGE;
  }

  private remember(lang: AppLanguage): void {
    try {
      this.storage()?.setItem(STORAGE_KEY, lang);
    } catch {
      // Stockage indisponible (navigation privée, cookies bloqués) : choix non mémorisé.
    }
  }

  private storage(): Storage | null {
    if (!this.isBrowser) {
      return null;
    }
    try {
      return this.document.defaultView?.localStorage ?? null;
    } catch {
      return null;
    }
  }
}
