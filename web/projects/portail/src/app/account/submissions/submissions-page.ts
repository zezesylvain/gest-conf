import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { Router, RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  ErrorSummary,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
  PublicEdition,
  Submission,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { callIsOpen, SubmissionsService } from './submissions.service';

/** « Mes soumissions » (plan L3 §5) : liste, état, échéance ; nouveau brouillon si l'appel
 * de l'édition courante est ouvert. */
@Component({
  selector: 'portail-submissions-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header
      [heading]="'portail.submissions.list.title' | translate"
      [lead]="'portail.submissions.list.lead' | translate"
    />
    <gc-error-summary [messages]="errors()" />

    @if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else {
      @if (meStore.me()?.profile_complete === false) {
        <p class="notice">
          {{ 'portail.submissions.list.profileIncomplete' | translate }}
          <a routerLink="/compte/profil">{{
            'portail.account.home.completeProfile' | translate
          }}</a>
        </p>
      }
      @if (edition(); as current) {
        <p class="actions">
          @if (open()) {
            <button
              mat-flat-button
              type="button"
              (click)="start(current)"
              [disabled]="busy() || meStore.me()?.profile_complete === false"
            >
              {{ 'portail.submissions.list.new' | translate: { edition: current.code } }}
            </button>
          } @else {
            <span class="hint">{{ 'portail.submissions.list.closed' | translate }}</span>
          }
        </p>
      }
      @if (submissions().length) {
        <!-- Défilement horizontal dans le cadre, jamais de la page (375 px). -->
        <div
          class="scroll"
          role="region"
          tabindex="0"
          [attr.aria-label]="'portail.submissions.list.title' | translate"
        >
          <table class="list">
            <thead>
              <tr>
                <th scope="col">{{ 'portail.submissions.fields.reference' | translate }}</th>
                <th scope="col">{{ 'portail.submissions.fields.title' | translate }}</th>
                <th scope="col">{{ 'portail.submissions.fields.status' | translate }}</th>
                <th scope="col">{{ 'portail.submissions.fields.deadline' | translate }}</th>
              </tr>
            </thead>
            <tbody>
              @for (item of submissions(); track item.id) {
                <tr>
                  <td>{{ item.reference || ('portail.submissions.draft' | translate) }}</td>
                  <td>
                    <a [routerLink]="['/compte/soumissions', item.id]">
                      {{ item.title || ('portail.submissions.untitled' | translate) }}
                    </a>
                  </td>
                  <td>{{ 'portail.submissions.status.' + item.status | translate }}</td>
                  <td>
                    @if (item.can_edit && item.deadline) {
                      {{ when(item.deadline) }}
                    } @else if (
                      item.allowed_actions.includes('final_version') &&
                      !item.final_version &&
                      item.final_deadline
                    ) {
                      {{
                        'portail.submissions.list.finalDue'
                          | translate: { date: when(item.final_deadline) }
                      }}
                    } @else {
                      —
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <p>{{ 'portail.submissions.list.empty' | translate }}</p>
      }
    }
  `,
  styles: `
    .scroll {
      overflow-x: auto;
    }
    .list {
      width: 100%;
      border-collapse: collapse;
    }
    .list th,
    .list td {
      text-align: left;
      padding: 0.5rem;
      border-bottom: 1px solid var(--gc-border);
      vertical-align: top;
    }
    .hint {
      color: var(--gc-muted);
    }
    .notice {
      border-left: 4px solid var(--gc-primary);
      padding-left: 0.75rem;
    }
  `,
})
export class SubmissionsPage implements OnInit {
  private readonly service = inject(SubmissionsService);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly language = inject(LanguageService);
  protected readonly meStore = inject(MeStore);

  protected readonly submissions = signal<Submission[]>([]);
  protected readonly edition = signal<PublicEdition | null>(null);
  protected readonly open = signal(false);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      const [submissions, edition] = await Promise.all([
        this.service.list(),
        this.service.currentEdition().catch(() => null),
      ]);
      this.submissions.set(submissions);
      this.edition.set(edition);
      this.open.set(!!edition && callIsOpen(edition));
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }

  protected when(iso: string): string {
    return formatInZone(iso, this.edition()?.timezone, this.language.current());
  }

  protected async start(edition: PublicEdition): Promise<void> {
    this.errors.set([]);
    this.busy.set(true);
    try {
      const created = await this.service.create(edition.code);
      await this.router.navigate(['/compte/soumissions', created.id]);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }
}
