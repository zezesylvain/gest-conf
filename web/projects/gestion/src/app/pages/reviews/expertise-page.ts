import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { ErrorSummary, LanguageService, PageHeader, ReviewerTrack } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { ReviewsApi } from '../../core/reviews-api';

/**
 * Expertises du relecteur pour l'édition (plan L4, H7) : thématiques de compétence, affichées
 * au président du CS lors de l'affectation.
 */
@Component({
  selector: 'gestion-expertise-page',
  imports: [TranslatePipe, MatButtonModule, MatCheckboxModule, PageHeader, ErrorSummary],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: '../page.scss',
  template: `
    <gc-page-header
      [heading]="'gestion.expertise.title' | translate"
      [lead]="'gestion.expertise.lead' | translate"
    />
    <div aria-live="polite">
      @if (status()) {
        <p class="notice" role="status">{{ status() }}</p>
      }
    </div>
    <gc-error-summary [messages]="errors()" />
    @if (!loading()) {
      <fieldset class="card">
        <legend>{{ 'gestion.expertise.tracks' | translate }}</legend>
        @for (track of available(); track track.code) {
          <div>
            <mat-checkbox [checked]="chosen().includes(track.code)" (change)="toggle(track.code)">
              {{ name(track) }}
            </mat-checkbox>
          </div>
        } @empty {
          <p class="muted">{{ 'gestion.expertise.none' | translate }}</p>
        }
        <div class="actions">
          <button mat-flat-button type="button" (click)="save()" [disabled]="busy()">
            {{ 'gestion.expertise.save' | translate }}
          </button>
        </div>
      </fieldset>
    }
  `,
})
export class ExpertisePage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ReviewsApi);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly available = signal<ReviewerTrack[]>([]);
  protected readonly chosen = signal<string[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  async ngOnInit(): Promise<void> {
    try {
      const expertise = await this.api.expertise(Number(this.editionId()));
      this.available.set(expertise.available);
      this.chosen.set(expertise.tracks);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected name(track: ReviewerTrack): string {
    return this.language.current() === 'en' && track.name_en ? track.name_en : track.name_fr;
  }

  protected toggle(code: string): void {
    this.chosen.update((codes) =>
      codes.includes(code) ? codes.filter((item) => item !== code) : [...codes, code],
    );
  }

  protected async save(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const expertise = await this.api.updateExpertise(Number(this.editionId()), this.chosen());
      this.chosen.set(expertise.tracks);
      this.status.set(this.translate.instant('gestion.expertise.saved'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
