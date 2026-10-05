import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { LanguageService, PublicationStatus } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { PortalApi } from '../../core/portal-api';

/**
 * Bandeau d'écart (E1) : le portail est pré-rendu au build ; une modification n'est
 * visible qu'à la mise en ligne suivante. Le bandeau le dit au lieu de le masquer.
 */
@Component({
  selector: 'gestion-portal-status-banner',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (state(); as current) {
      <div class="banner" [class.pending]="current.pending_changes > 0" role="status">
        @if (current.pending_changes > 0) {
          <p>
            <strong>{{
              'gestion.portal.status.pending' | translate: { count: current.pending_changes }
            }}</strong>
            @if (current.pending_since) {
              {{
                'gestion.portal.status.since' | translate: { date: format(current.pending_since) }
              }}
            }
          </p>
          <p>{{ 'gestion.portal.status.howTo' | translate }}</p>
        } @else {
          <p>{{ 'gestion.portal.status.upToDate' | translate }}</p>
        }
        <p class="muted">
          @if (current.last_published_at) {
            {{
              'gestion.portal.status.lastPublished'
                | translate: { date: format(current.last_published_at) }
            }}
          } @else {
            {{ 'gestion.portal.status.neverPublished' | translate }}
          }
        </p>
      </div>
    }
  `,
  styles: `
    .banner {
      display: grid;
      gap: 0.25rem;
      margin-bottom: 1rem;
      padding: 0.75rem 1rem;
      border-left: 4px solid #15803d;
      border-radius: 0.25rem;
      background: var(--gc-surface-muted);
    }
    .banner.pending {
      border-left-color: #b45309;
    }
    p {
      margin: 0;
    }
    .muted {
      color: var(--gc-muted);
      font-size: 0.9rem;
    }
  `,
})
export class PortalStatusBanner implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(PortalApi);
  private readonly language = inject(LanguageService);
  protected readonly state = signal<PublicationStatus | null>(null);

  async ngOnInit(): Promise<void> {
    await this.refresh();
  }

  /** Relu après chaque écriture de l'écran hôte. */
  async refresh(): Promise<void> {
    try {
      this.state.set(await this.api.status(Number(this.editionId())));
    } catch {
      // Bandeau informatif : son absence ne bloque pas l'écran.
    }
  }

  protected format(value: string): string {
    return new Intl.DateTimeFormat(this.language.current(), {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  }
}
