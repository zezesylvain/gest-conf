import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ApiStatus } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'portail-home-page',
  imports: [TranslatePipe, ApiStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="hero" aria-labelledby="home-title">
      <h1 id="home-title">{{ 'portail.home.heading' | translate }}</h1>
      <p class="lead">{{ 'portail.home.lead' | translate }}</p>
      <p>
        <!-- Lien classique (pas routerLink) : « gestion » est une autre application Angular. -->
        <a class="cta" href="/gestion/">{{ 'portail.home.managementLink' | translate }}</a>
      </p>
      <gc-api-status />
    </section>
  `,
  styles: `
    .hero {
      display: grid;
      gap: 1rem;
    }
    h1 {
      margin: 0;
      font-size: clamp(1.75rem, 4vw, 2.5rem);
    }
    .lead {
      margin: 0;
      font-size: 1.125rem;
      color: var(--gc-muted);
    }
    .cta {
      color: var(--gc-primary);
      font-weight: 600;
    }
  `,
})
export class HomePage {}
