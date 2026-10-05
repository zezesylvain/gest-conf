import { inject, Injectable } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Title } from '@angular/platform-browser';
import { RouterStateSnapshot, TitleStrategy } from '@angular/router';
import { TranslateService } from '@ngx-translate/core';

/**
 * Titre de page traduit (WCAG 2.4.2) : la propriété « title » des routes contient
 * une clé de traduction, jamais un texte en dur. Le titre suit le changement de langue.
 */
@Injectable()
export class TranslatedTitleStrategy extends TitleStrategy {
  private readonly title = inject(Title);
  private readonly translate = inject(TranslateService);
  private snapshot: RouterStateSnapshot | null = null;

  constructor() {
    super();
    this.translate.onLangChange.pipe(takeUntilDestroyed()).subscribe(() => this.apply());
  }

  override updateTitle(snapshot: RouterStateSnapshot): void {
    this.snapshot = snapshot;
    this.apply();
  }

  private apply(): void {
    const appName = this.translate.instant('shared.appName');
    const key = this.snapshot ? this.buildTitle(this.snapshot) : undefined;
    this.title.setTitle(key ? `${this.translate.instant(key)} · ${appName}` : appName);
  }
}
