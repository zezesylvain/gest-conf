import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ErrorSummary, fieldErrorMessage, MeStore, PageHeader } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';

/**
 * Confidentialité et paramètres de l'évaluation (plan L1 §6.1 ; plan L4 H4, H6, H12) : double
 * aveugle (RG-04), relecteurs par soumission, charge maximale par relecteur, seuil de
 * divergence, note finale pondérée par la confiance. Changement **critique** : réauthentification récente exigée (la fenêtre
 * s'ouvre d'elle-même), audit avant/après. RG-19 : après la première soumission, le double
 * aveugle est gelé ; seul un administrateur le change, avec un motif (`setting_frozen`).
 */
@Component({
  selector: 'gestion-confidentiality-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'gestion.settings.confidentiality.title' | translate" />
    @if (!canWrite()) {
      <p class="notice">{{ 'gestion.settings.readOnly' | translate }}</p>
    }
    <div aria-live="polite">
      @if (saved()) {
        <p class="notice" role="status">{{ 'gestion.settings.saved' | translate }}</p>
      }
    </div>
    <gc-error-summary [messages]="errors()" />
    @if (!loading()) {
      <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
        <mat-checkbox formControlName="double_blind">
          {{ 'gestion.settings.confidentiality.doubleBlind' | translate }}
        </mat-checkbox>
        <p class="muted">{{ 'gestion.settings.confidentiality.doubleBlindHint' | translate }}</p>
        @if (frozen().includes('double_blind')) {
          <p class="notice">
            {{
              (isAdmin() ? 'gestion.settings.frozen.admin' : 'gestion.settings.frozen.locked')
                | translate
            }}
          </p>
        }
        @if (frozenChange()) {
          <mat-form-field appearance="outline">
            <mat-label>{{ 'gestion.settings.frozen.reason' | translate }}</mat-label>
            <textarea matInput formControlName="reason" rows="2" required></textarea>
            <mat-error>{{ 'shared.form.required' | translate }}</mat-error>
          </mat-form-field>
        }
        <mat-form-field appearance="outline">
          <mat-label>{{ 'gestion.settings.confidentiality.reviewers' | translate }}</mat-label>
          <input
            matInput
            type="number"
            formControlName="reviewers_per_submission"
            min="1"
            max="10"
          />
          <mat-error>{{ error('reviewers_per_submission') }}</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>{{ 'gestion.settings.confidentiality.maxReviews' | translate }}</mat-label>
          <input
            matInput
            type="number"
            formControlName="max_reviews_per_reviewer"
            min="1"
            max="100"
          />
          <mat-hint>{{ 'gestion.settings.confidentiality.maxReviewsHint' | translate }}</mat-hint>
          <mat-error>{{ error('max_reviews_per_reviewer') }}</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>{{ 'gestion.settings.confidentiality.divergence' | translate }}</mat-label>
          <input
            matInput
            type="number"
            formControlName="divergence_threshold"
            min="0"
            max="100"
            step="0.01"
          />
          <mat-hint>{{ 'gestion.settings.confidentiality.divergenceHint' | translate }}</mat-hint>
          <mat-error>{{ error('divergence_threshold') }}</mat-error>
        </mat-form-field>
        <mat-checkbox formControlName="confidence_weighted_score">
          {{ 'gestion.settings.confidentiality.confidenceWeighted' | translate }}
        </mat-checkbox>
        <p class="muted">
          {{ 'gestion.settings.confidentiality.confidenceWeightedHint' | translate }}
        </p>
        @if (canWrite()) {
          <p class="muted">{{ 'gestion.settings.confidentiality.sensitive' | translate }}</p>
          <div class="actions">
            <button mat-flat-button type="submit" [disabled]="saving()">
              {{ 'gestion.settings.save' | translate }}
            </button>
          </div>
        }
      </form>
    }
  `,
  styleUrl: '../page.scss',
  styles: `
    mat-form-field[subscriptsizing='dynamic'] {
      margin-bottom: 0.75rem;
    }
  `,
})
export class ConfidentialityPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);

  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.write'),
  );
  /** Indice d'ergonomie : `edition.archive` n'appartient qu'à l'administrateur (§5.2). */
  protected readonly isAdmin = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.archive'),
  );
  protected readonly frozen = signal<string[]>([]);
  private initialDoubleBlind = true;
  protected readonly form = inject(NonNullableFormBuilder).group({
    double_blind: [true],
    reviewers_per_submission: [3, [Validators.required, Validators.min(1), Validators.max(10)]],
    max_reviews_per_reviewer: [10, [Validators.required, Validators.min(1), Validators.max(100)]],
    divergence_threshold: [30, [Validators.required, Validators.min(0), Validators.max(100)]],
    confidence_weighted_score: [false],
    reason: ['', Validators.maxLength(2000)],
  });
  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      const value = await this.api.confidentiality(Number(this.editionId()));
      this.form.reset({
        double_blind: value.double_blind ?? true,
        reviewers_per_submission: value.reviewers_per_submission ?? 3,
        max_reviews_per_reviewer: value.max_reviews_per_reviewer ?? 10,
        divergence_threshold: Number(value.divergence_threshold ?? 30),
        confidence_weighted_score: value.confidence_weighted_score ?? false,
        reason: '',
      });
      this.initialDoubleBlind = value.double_blind ?? true;
      this.frozen.set(value.frozen_fields);
      if (!this.canWrite()) {
        this.form.disable();
      } else if (value.frozen_fields.includes('double_blind') && !this.isAdmin()) {
        this.form.controls.double_blind.disable();
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected error(
    name: 'reviewers_per_submission' | 'max_reviews_per_reviewer' | 'divergence_threshold',
  ): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  /** Changement d'un réglage gelé (RG-19) : un motif est exigé. */
  protected frozenChange(): boolean {
    return (
      this.frozen().includes('double_blind') &&
      this.form.controls.double_blind.value !== this.initialDoubleBlind
    );
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    this.saved.set(false);
    if (this.frozenChange() && !this.form.controls.reason.value.trim()) {
      this.form.controls.reason.setErrors({ required: true });
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    try {
      const { reason, divergence_threshold, ...value } = this.form.getRawValue();
      const saved = await this.api.updateConfidentiality(Number(this.editionId()), {
        ...value,
        // Décimal côté serveur : transmis en chaîne, comme le schéma le décrit.
        divergence_threshold: String(divergence_threshold),
        ...(this.frozenChange() ? { reason: reason.trim() } : {}),
      });
      this.initialDoubleBlind = saved.double_blind ?? value.double_blind;
      this.form.controls.reason.reset('');
      this.saved.set(true);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.saving.set(false);
    }
  }
}
