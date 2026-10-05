import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { HelpSheet } from './help-sheets';

/**
 * Gabarit unique d'une fiche d'aide, rendu par la page `/aide` **et** par le tiroir « ? ».
 * Seule la page pose l'ancre (`anchor`) : un même `id` dans la page et le tiroir donnerait
 * deux éléments pour une ancre.
 */
@Component({
  selector: 'gestion-help-sheet',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let item = sheet();
    <article
      class="sheet"
      [attr.id]="anchor() ? 'fiche-' + item.id : null"
      [attr.aria-labelledby]="headingId()"
    >
      @if (anchor()) {
        <h2 [id]="headingId()">{{ item.title | translate }}</h2>
      } @else {
        <h2 [id]="headingId()" tabindex="-1">{{ item.title | translate }}</h2>
      }
      <p class="summary">{{ item.summary | translate }}</p>
      <p class="path">
        <span class="label">{{ 'gestion.help.access' | translate }}</span>
        {{ item.path | translate }}
      </p>
      @for (block of item.blocks; track $index) {
        @switch (block.type) {
          @case ('text') {
            <p>{{ block.text | translate }}</p>
          }
          @case ('list') {
            <ul>
              @for (entry of block.items; track entry) {
                <li>{{ entry | translate }}</li>
              }
            </ul>
          }
          @case ('steps') {
            <ol class="steps">
              @for (step of block.steps; track step.title) {
                <li>
                  <strong>{{ step.title | translate }}</strong>
                  <span>{{ step.body | translate }}</span>
                </li>
              }
            </ol>
          }
          @case ('callout') {
            <aside class="callout" [class]="block.tone">
              <p class="callout-title">
                <span class="visually-hidden"
                  >{{ 'gestion.help.tones.' + block.tone | translate }} :
                </span>
                {{ block.title | translate }}
              </p>
              <p>{{ block.text | translate }}</p>
            </aside>
          }
        }
      }
    </article>
  `,
  styles: `
    .sheet {
      display: grid;
      gap: 0.5rem;
      scroll-margin-top: 1.5rem;
    }
    h2 {
      margin: 0;
      font-size: 1.25rem;
    }
    p {
      margin: 0;
    }
    .summary {
      color: var(--gc-muted);
    }
    .path {
      font-size: 0.9rem;
    }
    .label {
      font-weight: 700;
    }
    ul,
    ol {
      margin: 0;
      padding-left: 1.25rem;
      display: grid;
      gap: 0.35rem;
    }
    .steps li {
      display: grid;
      gap: 0.1rem;
    }
    .callout {
      display: grid;
      gap: 0.25rem;
      padding: 0.6rem 0.75rem;
      border-left: 4px solid var(--gc-primary);
      border-radius: 0.25rem;
      background: var(--gc-surface-muted);
    }
    .callout-title {
      font-weight: 700;
    }
    .callout.tip {
      border-left-color: #15803d;
    }
    .callout.warning {
      border-left-color: #b45309;
    }
    .callout.danger {
      border-left-color: #b91c1c;
    }
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }
    @media print {
      .callout {
        background: transparent;
      }
      .sheet {
        break-inside: avoid;
      }
    }
  `,
})
export class HelpSheetView {
  readonly sheet = input.required<HelpSheet>();
  /** Vrai dans la page `/aide` : pose l'ancre `fiche-<id>`. */
  readonly anchor = input(false);

  protected headingId(): string {
    return `${this.anchor() ? 'fiche' : 'tiroir'}-${this.sheet().id}-titre`;
  }
}
