import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  inject,
  input,
} from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/**
 * Résumé des erreurs d'un formulaire (WCAG 2.1 AA, plan §10.5) : annoncé par les lecteurs
 * d'écran (`role="alert"`) et focalisable quand il apparaît.
 */
@Component({
  selector: 'gc-error-summary',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (messages().length) {
      <div class="gc-error-summary" role="alert" tabindex="-1">
        <p class="gc-error-summary__title">{{ 'shared.form.errorSummary' | translate }}</p>
        <ul>
          @for (message of messages(); track $index) {
            <li>{{ message }}</li>
          }
        </ul>
      </div>
    }
  `,
  styles: `
    .gc-error-summary {
      margin: 0 0 1rem;
      padding: 0.75rem 1rem;
      border-left: 0.35rem solid var(--gc-danger);
      background: #fef2f2;
      color: var(--gc-text);
    }
    .gc-error-summary__title {
      margin: 0 0 0.25rem;
      font-weight: 600;
    }
    ul {
      margin: 0;
      padding-left: 1.25rem;
    }
  `,
})
export class ErrorSummary {
  readonly messages = input<string[]>([]);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  constructor() {
    effect(() => {
      if (this.messages().length) {
        queueMicrotask(() =>
          this.host.nativeElement.querySelector<HTMLElement>('.gc-error-summary')?.focus(),
        );
      }
    });
  }
}
