import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { PageHeader } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

/** Accès refusé (garde ergonomique ou 403 du serveur). */
@Component({
  selector: 'gestion-forbidden-page',
  imports: [RouterLink, TranslatePipe, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'gestion.forbidden.title' | translate" />
    <p>{{ 'gestion.forbidden.lead' | translate }}</p>
    <p>
      <a routerLink="/editions">{{ 'gestion.forbidden.backToEditions' | translate }}</a>
    </p>
  `,
  styles: `
    a {
      color: var(--gc-primary);
    }
  `,
})
export class ForbiddenPage {}
