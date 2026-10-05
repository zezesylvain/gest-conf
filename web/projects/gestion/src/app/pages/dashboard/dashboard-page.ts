import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ApiStatus } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'gestion-dashboard-page',
  imports: [TranslatePipe, ApiStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1>{{ 'gestion.dashboard.heading' | translate }}</h1>
    <p>{{ 'gestion.dashboard.lead' | translate }}</p>
    <gc-api-status />
  `,
})
export class DashboardPage {}
