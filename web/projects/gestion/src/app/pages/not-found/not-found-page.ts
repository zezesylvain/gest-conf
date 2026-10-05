import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'gestion-not-found-page',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1>{{ 'gestion.notFound.heading' | translate }}</h1>
    <p>
      <a routerLink="/">{{ 'gestion.notFound.backHome' | translate }}</a>
    </p>
  `,
})
export class NotFoundPage {}
