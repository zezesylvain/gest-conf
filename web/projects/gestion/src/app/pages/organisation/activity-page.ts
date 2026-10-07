import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ActivityEntry,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { OrganisationApi } from '../../core/organisation-api';
import { errorMessages } from '../../core/page-support';

/** Actions du fil traduites (liste blanche du serveur, N14) ; une autre reste en code. */
export const ACTIVITY_ACTIONS: readonly string[] = [
  'task.created',
  'task.updated',
  'task.commented',
  'task.archived',
  'task.restored',
  'task.attachment_added',
  'task.attachment_removed',
  'shift.created',
  'shift.updated',
  'shift.deleted',
  'shift.assigned',
  'shift.unassigned',
  'meal.created',
  'meal.updated',
  'meal.deleted',
  'announcement.published',
  'announcement.withdrawn',
  'survey.published',
  'program.published',
  'portal.published',
  'edition.status_changed',
];

/**
 * Fil d'activité du CO (plan L8, N14 ; `tasks.read`) : les 50 dernières actions d'une liste
 * blanche, sans valeur avant ni après ; une tâche se rouvre d'un clic.
 */
@Component({
  selector: 'gestion-activity-page',
  imports: [RouterLink, TranslatePipe, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './activity-page.html',
  styleUrl: '../page.scss',
})
export class ActivityPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(OrganisationApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly entries = signal<ActivityEntry[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.entries.set(await this.api.activity(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected action(entry: ActivityEntry): string {
    return ACTIVITY_ACTIONS.includes(entry.action)
      ? this.translate.instant(`gestion.activity.actions.${entry.action.replace('.', '_')}`)
      : entry.action;
  }

  protected isTask(entry: ActivityEntry): boolean {
    return entry.object_type === 'logistics.task' && !!entry.object_id;
  }
}
