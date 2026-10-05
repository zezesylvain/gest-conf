import { afterNextRender, ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { TranslatePipe } from '@ngx-translate/core';

import { Api, health } from '../api';

export type ApiState = 'checking' | 'ok' | 'degraded' | 'unreachable';

/** Indicateur de disponibilité de l'API : valide la chaîne Angular → /api → Django → MariaDB. */
@Component({
  selector: 'gc-api-status',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p class="gc-api-status" role="status" [attr.data-state]="state()">
      {{ 'shared.apiStatus.' + state() | translate }}
    </p>
  `,
  styles: `
    .gc-api-status {
      display: inline-block;
      margin: 0;
      padding: 0.25rem 0.75rem;
      border-left: 0.35rem solid #6b7280;
      background: #f3f4f6;
      color: #111827;
    }
    .gc-api-status[data-state='ok'] {
      border-color: #15803d;
    }
    .gc-api-status[data-state='degraded'] {
      border-color: #b45309;
    }
    .gc-api-status[data-state='unreachable'] {
      border-color: #b91c1c;
    }
  `,
})
export class ApiStatus {
  private readonly api = inject(Api);

  protected readonly state = signal<ApiState>('checking');

  constructor() {
    // Navigateur uniquement : aucun appel d'API pendant le pré-rendu (SSG).
    afterNextRender(() => void this.check());
  }

  async check(): Promise<void> {
    try {
      const result = await this.api.invoke(health);
      this.state.set(result.status === 'ok' ? 'ok' : 'degraded');
    } catch (error) {
      const degraded = error instanceof HttpErrorResponse && error.status === 503;
      this.state.set(degraded ? 'degraded' : 'unreachable');
    }
  }
}
