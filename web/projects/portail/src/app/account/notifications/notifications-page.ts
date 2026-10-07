import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  ErrorSummary,
  formatInZone,
  LanguageService,
  Notification,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { NotificationsStore } from './notifications.store';

/**
 * Notifications de l'espace compte (plan L3, F13) : le texte est composé ici à partir de la
 * nature et des éléments transmis (référence, titre, échéance), dans la langue courante.
 * Une notification liée à une de ses soumissions ouvre celle-ci et devient lue ; celles du
 * lot L8 mènent au questionnaire ou à l'écran de la gestion (tâche, « Mon planning »).
 */
@Component({
  selector: 'portail-notifications-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.notifications.title' | translate" />
    <gc-error-summary [messages]="errors()" />
    @if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else {
      @if (store.unread() > 0) {
        <p class="actions">
          <button mat-stroked-button type="button" (click)="markAll()" [disabled]="busy()">
            {{ 'portail.notifications.markAll' | translate }}
          </button>
        </p>
      }
      @if (items().length) {
        <ul class="list">
          @for (item of items(); track item.id) {
            <li [class.unread]="!item.read_at">
              @if (!item.read_at) {
                <span class="visually-hidden">{{
                  'portail.notifications.unread' | translate
                }}</span>
              }
              <span>{{ text(item) }}</span>
              <time class="when" [attr.datetime]="item.created_at">{{
                when(item.created_at)
              }}</time>
              @if (item.payload['submission_id']) {
                <a
                  [routerLink]="['/compte/soumissions', item.payload['submission_id']]"
                  (click)="open(item)"
                >
                  {{ 'portail.notifications.open' | translate }}
                </a>
              } @else if (item.payload['survey_id']) {
                <a
                  [routerLink]="['/compte/questionnaires', item.payload['survey_id']]"
                  (click)="open(item)"
                >
                  {{ 'portail.notifications.openSurvey' | translate }}
                </a>
              } @else if (management(item); as href) {
                <!-- Tâche ou poste de bénévolat : écran de la gestion (autre application). -->
                <a [href]="href" (click)="open(item)">
                  {{ 'portail.notifications.openManagement' | translate }}
                </a>
              }
            </li>
          }
        </ul>
      } @else {
        <p>{{ 'portail.notifications.empty' | translate }}</p>
      }
    }
  `,
  styles: `
    .list {
      display: grid;
      gap: 0.5rem;
      padding: 0;
      list-style: none;
    }
    .list li {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 0.75rem;
      padding: 0.75rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.25rem;
    }
    .list li.unread {
      border-left: 4px solid var(--gc-primary);
      font-weight: 600;
    }
    .when {
      color: var(--gc-muted);
      font-weight: 400;
    }
    a {
      color: var(--gc-primary);
    }
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
})
export class NotificationsPage implements OnInit {
  protected readonly store = inject(NotificationsStore);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly items = signal<Notification[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    await this.load();
  }

  protected text(item: Notification): string {
    const payload = item.payload as Record<string, string | undefined>;
    // Annonces et questionnaires (plan L8) : titre dans la langue courante, français sinon.
    const localized =
      (this.language.current() === 'en' && payload['title_en']) || payload['title_fr'];
    return this.translate.instant(`portail.notifications.kinds.${item.kind}`, {
      reference: payload['reference'] || this.translate.instant('portail.submissions.draft'),
      title:
        payload['title'] || localized || this.translate.instant('portail.submissions.untitled'),
      edition: payload['edition_code'] ?? '',
      until: payload['until'] ? this.when(payload['until']) : '',
      closes: payload['closes_at'] ? this.when(payload['closes_at']) : '',
      starts: payload['starts_at'] ? this.when(payload['starts_at']) : '',
    });
  }

  /**
   * Lien vers la gestion (plan L8) : tâche confiée, poste de bénévolat confié ou retiré.
   * Les droits restent vérifiés par la gestion et le serveur (règle n° 2).
   */
  protected management(item: Notification): string | null {
    const payload = item.payload as Record<string, string | number | undefined>;
    const edition = payload['edition_id'];
    if (!edition) return null;
    if (item.kind === 'task_assigned' && payload['task_id']) {
      return `/gestion/editions/${edition}/organisation/taches/${payload['task_id']}`;
    }
    if (item.kind === 'shift_assigned' || item.kind === 'shift_removed') {
      return `/gestion/editions/${edition}/jour-j/mon-planning`;
    }
    return null;
  }

  protected when(iso: string): string {
    return formatInZone(iso, undefined, this.language.current());
  }

  protected async markAll(): Promise<void> {
    this.busy.set(true);
    try {
      await this.store.markRead();
      await this.load();
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }

  protected open(item: Notification): void {
    if (!item.read_at) {
      void this.store.markRead([item.id]).catch(() => undefined);
    }
  }

  private async load(): Promise<void> {
    this.errors.set([]);
    try {
      this.items.set((await this.store.list()).results);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }
}
