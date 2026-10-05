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
 * Confidentialité de l'évaluation (plan L1 §6.1) : double aveugle (RG-04) et relecteurs par
 * soumission. Changement **critique** : réauthentification récente exigée (la fenêtre
 * s'ouvre d'elle-même), audit avant/après. Le gel après l'ouverture de l'appel arrive en L3.
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
        <mat-form-field appearance="outline">
          <mat-label>{{ 'gestion.settings.confidentiality.reviewers' | translate }}</mat-label>
          <input
            matInput
            type="number"
            formControlName="reviewers_per_submission"
            min="1"
            max="10"
          />
          <mat-error>{{ error() }}</mat-error>
        </mat-form-field>
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
})
export class ConfidentialityPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);

  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('edition.write'),
  );
  protected readonly form = inject(NonNullableFormBuilder).group({
    double_blind: [true],
    reviewers_per_submission: [3, [Validators.required, Validators.min(1), Validators.max(10)]],
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
      });
      if (!this.canWrite()) {
        this.form.disable();
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected error(): string {
    return fieldErrorMessage(this.translate, this.form.controls.reviewers_per_submission);
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    this.saved.set(false);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    try {
      await this.api.updateConfidentiality(Number(this.editionId()), this.form.getRawValue());
      this.saved.set(true);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.saving.set(false);
    }
  }
}
