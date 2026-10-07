import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Diet, ErrorSummary, MyDietary } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunityService } from './community.service';
import { ALLERGIES_MAX, DIETS, messagesOf } from './community-support';

/**
 * Carte « Régime alimentaire » d'une édition (plan L8, N7, **RG-23**) : facultative, avec un
 * **consentement explicite** à chaque déclaration (la donnée peut révéler la santé ou des
 * convictions), retirée à tout moment ; effacée 30 jours après l'édition. Rien ne s'affiche
 * pour qui n'est ni inscrit, ni intervenant, ni membre d'un comité, ni bénévole.
 */
@Component({
  selector: 'portail-dietary-card',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dietary(); as current) {
      @if (current.eligible) {
        <section class="card" [attr.aria-labelledby]="'dietary-' + editionId()">
          <h2 [id]="'dietary-' + editionId()">
            {{ 'portail.community.dietary.title' | translate }}
            @if (editionLabel()) {
              <span class="muted">— {{ editionLabel() }}</span>
            }
          </h2>
          <p>{{ 'portail.community.dietary.lead' | translate }}</p>
          <div aria-live="polite">
            @if (status()) {
              <p class="notice" role="status">{{ status() }}</p>
            }
          </div>
          <gc-error-summary [messages]="errors()" />
          <form [formGroup]="form" (ngSubmit)="save()">
            <fieldset>
              <legend>{{ 'portail.community.dietary.diets' | translate }}</legend>
              @for (item of diets; track item) {
                <mat-checkbox
                  [checked]="selected().includes(item)"
                  (change)="toggle(item, $event.checked)"
                  >{{ 'portail.community.diet.' + item | translate }}</mat-checkbox
                >
              }
            </fieldset>
            <mat-form-field class="wide">
              <mat-label>{{ 'portail.community.dietary.allergies' | translate }}</mat-label>
              <textarea
                matInput
                formControlName="allergies"
                rows="2"
                [attr.maxlength]="allergiesMax"
              ></textarea>
              <mat-hint>{{ 'portail.community.dietary.allergiesHint' | translate }}</mat-hint>
            </mat-form-field>
            <mat-checkbox formControlName="consent" required>{{
              'portail.community.dietary.consent' | translate
            }}</mat-checkbox>
            @if (form.controls.consent.touched && !form.controls.consent.value) {
              <p class="error" role="alert">
                {{ 'portail.community.dietary.consentRequired' | translate }}
              </p>
            }
            <p class="actions">
              <button mat-flat-button type="submit" [disabled]="busy()">
                {{ 'portail.community.dietary.save' | translate }}
              </button>
              @if (current.consented_at) {
                <button mat-button type="button" (click)="withdraw()" [disabled]="busy()">
                  {{ 'portail.community.dietary.withdraw' | translate }}
                </button>
              }
            </p>
          </form>
          <p class="muted">{{ 'portail.community.dietary.retention' | translate }}</p>
        </section>
      }
    }
  `,
  styles: `
    fieldset {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
      margin-bottom: 1rem;
    }
    .wide {
      width: 100%;
    }
    .muted {
      color: var(--gc-muted);
      font-weight: 400;
    }
    .error {
      color: var(--gc-danger);
    }
    .actions {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
  `,
})
export class DietaryCard implements OnInit {
  readonly editionId = input.required<number>();
  readonly editionLabel = input('');

  private readonly service = inject(CommunityService);
  private readonly translate = inject(TranslateService);

  protected readonly diets = DIETS;
  protected readonly allergiesMax = ALLERGIES_MAX;
  protected readonly dietary = signal<MyDietary | null>(null);
  protected readonly selected = signal<Diet[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  protected readonly form = inject(NonNullableFormBuilder).group({
    allergies: ['', Validators.maxLength(ALLERGIES_MAX)],
    consent: [false, Validators.requiredTrue],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.show(await this.service.dietary(this.editionId()));
    } catch {
      // Carte facultative : sans réponse, elle ne s'affiche pas.
      this.dietary.set(null);
    }
  }

  protected toggle(item: Diet, checked: boolean): void {
    const current = this.selected().filter((diet) => diet !== item);
    this.selected.set(checked ? [...current, item] : current);
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    await this.run('portail.community.dietary.saved', () =>
      this.service.declareDietary(this.editionId(), {
        diets: this.selected(),
        allergies: this.form.getRawValue().allergies.trim(),
        consent: true,
      }),
    );
  }

  protected async withdraw(): Promise<void> {
    await this.run('portail.community.dietary.withdrawn', () =>
      this.service.withdrawDietary(this.editionId()),
    );
  }

  private async run(message: string, action: () => Promise<MyDietary>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.show(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private show(dietary: MyDietary): void {
    this.dietary.set(dietary);
    this.selected.set([...dietary.diets]);
    // Le consentement se donne à chaque déclaration : la case revient décochée.
    this.form.reset({ allergies: dietary.allergies, consent: false });
  }
}
