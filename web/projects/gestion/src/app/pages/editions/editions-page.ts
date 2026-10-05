import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LanguageService, MeStore, PageHeader } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { editionTitle, managedEditions } from '../../core/managed-editions';

/** Sélecteur d'édition (plan L1 §5.8, §10.3) : éditions où l'on a une capacité. */
@Component({
  selector: 'gestion-editions-page',
  imports: [RouterLink, TranslatePipe, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'gestion.editions.title' | translate" />
    @if (editions().length) {
      <ul class="editions">
        @for (edition of editions(); track edition.id) {
          <li>
            <a [routerLink]="['/editions', edition.id]">
              <strong>{{ edition.code }}</strong> — {{ title(edition) }} ({{ edition.year }})
            </a>
            <span class="badge">{{ 'gestion.status.' + edition.status | translate }}</span>
          </li>
        }
      </ul>
    } @else {
      <p>{{ 'gestion.editions.none' | translate }}</p>
      <p>
        <a href="/compte">{{ 'gestion.editions.toAccount' | translate }}</a>
      </p>
    }
  `,
  styles: `
    .editions {
      list-style: none;
      padding: 0;
      display: grid;
      gap: 0.75rem;
    }
    a {
      color: var(--gc-primary);
    }
    .badge {
      margin-left: 0.5rem;
      font-size: 0.85rem;
      padding: 0.1rem 0.5rem;
      border: 1px solid var(--gc-border);
      border-radius: 1rem;
    }
  `,
})
export class EditionsPage {
  private readonly meStore = inject(MeStore);
  private readonly language = inject(LanguageService);
  protected readonly editions = computed(() => managedEditions(this.meStore));

  protected title(edition: { title_fr: string; title_en?: string }): string {
    return editionTitle(edition, this.language.current());
  }
}
