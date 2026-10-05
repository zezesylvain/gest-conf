import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { LanguageService } from './language.service';
import { AppLanguage } from './languages';

@Component({
  selector: 'gc-language-switcher',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="gc-language-switcher"
      role="group"
      [attr.aria-label]="'shared.language.label' | translate"
    >
      @for (lang of language.languages; track lang) {
        <button
          type="button"
          [attr.lang]="lang"
          [attr.aria-pressed]="lang === language.current()"
          (click)="select(lang)"
        >
          {{ 'shared.language.' + lang | translate }}
        </button>
      }
    </div>
  `,
  styles: `
    .gc-language-switcher {
      display: flex;
      gap: 0.25rem;
    }
    button {
      font: inherit;
      padding: 0.25rem 0.6rem;
      border: 1px solid currentColor;
      border-radius: 0.25rem;
      background: transparent;
      color: inherit;
      cursor: pointer;
    }
    button[aria-pressed='true'] {
      font-weight: 700;
      text-decoration: underline;
    }
    button:focus-visible {
      outline: 3px solid currentColor;
      outline-offset: 2px;
    }
  `,
})
export class LanguageSwitcher {
  protected readonly language = inject(LanguageService);

  protected select(lang: AppLanguage): void {
    void this.language.use(lang);
  }
}
