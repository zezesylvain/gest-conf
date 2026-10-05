import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** En-tête de page : titre (h1) et chapeau facultatif. */
@Component({
  selector: 'gc-page-header',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="gc-page-header">
      <h1>{{ heading() }}</h1>
      @if (lead()) {
        <p class="gc-page-header__lead">{{ lead() }}</p>
      }
    </header>
  `,
  styles: `
    .gc-page-header {
      margin-bottom: 1.5rem;
    }
    h1 {
      margin: 0 0 0.5rem;
      font-size: clamp(1.5rem, 3vw, 2rem);
    }
    .gc-page-header__lead {
      margin: 0;
      color: var(--gc-muted);
    }
  `,
})
export class PageHeader {
  readonly heading = input.required<string>();
  readonly lead = input<string>('');
}
