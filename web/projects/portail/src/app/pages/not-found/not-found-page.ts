import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'portail-not-found-page',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1>{{ 'portail.notFound.heading' | translate }}</h1>
    <p>
      <a routerLink="/">{{ 'portail.notFound.backHome' | translate }}</a>
    </p>
  `,
})
export class NotFoundPage {}
