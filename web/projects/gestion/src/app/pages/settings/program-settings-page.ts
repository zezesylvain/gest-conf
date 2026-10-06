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

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { ProgramApi } from '../../core/program-api';

/**
 * Paramétrage › Programme (plan L5, I17) : tampon entre les créneaux d'une session (0 à
 * 30 minutes, RG-13) et RG-11 (présentateur inscrit), désactivée par défaut et sans effet
 * avant les inscriptions (L6). Lecture `program.read`, écriture `program.write`.
 */
@Component({
  selector: 'gestion-program-settings-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header
      [heading]="'gestion.settings.program.title' | translate"
      [lead]="'gestion.settings.program.lead' | translate"
    />
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
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>{{ 'gestion.settings.program.buffer' | translate }}</mat-label>
          <input matInput type="number" min="0" max="30" formControlName="session_buffer_minutes" />
          <mat-hint>{{ 'gestion.settings.program.bufferHint' | translate }}</mat-hint>
          <mat-error>{{ error('session_buffer_minutes') }}</mat-error>
        </mat-form-field>
        <mat-checkbox formControlName="presenter_registration_required">
          {{ 'gestion.settings.program.registration' | translate }}
        </mat-checkbox>
        <p class="muted">{{ 'gestion.settings.program.registrationHint' | translate }}</p>
        @if (canWrite()) {
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
    mat-checkbox {
      margin-top: 1rem;
    }
  `,
})
export class ProgramSettingsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(ProgramApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(NonNullableFormBuilder);

  protected readonly loading = signal(true);
  protected readonly saving = signal(false);
  protected readonly saved = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('program.write'),
  );
  protected readonly form = this.fb.group({
    session_buffer_minutes: [0, [Validators.required, Validators.min(0), Validators.max(30)]],
    presenter_registration_required: [false],
  });

  async ngOnInit(): Promise<void> {
    try {
      const settings = await this.api.settings(Number(this.editionId()));
      this.form.reset({
        session_buffer_minutes: settings.session_buffer_minutes ?? 0,
        presenter_registration_required: settings.presenter_registration_required ?? false,
      });
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    if (!this.canWrite()) {
      this.form.disable();
    }
    this.loading.set(false);
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected async submit(): Promise<void> {
    this.saved.set(false);
    this.errors.set([]);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    try {
      await this.api.updateSettings(Number(this.editionId()), this.form.getRawValue());
      this.saved.set(true);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.saving.set(false);
    }
  }
}
