import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  BillingProfile,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { RegistrationsApi } from '../../core/registrations-api';

const PREFIX = /^[A-Z][A-Z0-9]{0,7}$/;
const RATE = /^\d{1,3}(\.\d{1,2})?$/;

/**
 * Mentions de facturation de l'édition (plan L6, J8 ; Q8 ouverte) : raison sociale,
 * adresse, identifiants, TVA (taux ou mention d'exonération), coordonnées bancaires des pro
 * forma, préfixes des séries (figés dès la première pièce de leur série). Sans raison sociale
 * ni adresse, aucune facture ne s'émet : les inscriptions confirmées attendent, puis
 * « Émettre les factures en attente ». Lecture `finance.read` ; écriture `pricing.write`,
 * avec réauthentification récente.
 */
@Component({
  selector: 'gestion-billing-profile-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './billing-profile-page.html',
  styleUrl: '../page.scss',
})
export class BillingProfilePage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);

  protected readonly profile = signal<BillingProfile | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('pricing.write'),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    legal_name: ['', Validators.maxLength(255)],
    address: [''],
    tax_identifiers: [''],
    vat_rate: ['', Validators.pattern(RATE)],
    vat_note: ['', Validators.maxLength(255)],
    bank_details: [''],
    footer: [''],
    invoice_prefix: ['F', [Validators.required, Validators.pattern(PREFIX)]],
    credit_note_prefix: ['AV', [Validators.required, Validators.pattern(PREFIX)]],
    proforma_prefix: ['PF', [Validators.required, Validators.pattern(PREFIX)]],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.setProfile(await this.api.billingProfile(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
    if (!this.canWrite()) {
      this.form.disable();
    }
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  private setProfile(profile: BillingProfile): void {
    this.profile.set(profile);
    this.form.reset({
      legal_name: profile.legal_name ?? '',
      address: profile.address ?? '',
      tax_identifiers: profile.tax_identifiers ?? '',
      vat_rate: profile.vat_rate ?? '',
      vat_note: profile.vat_note ?? '',
      bank_details: profile.bank_details ?? '',
      footer: profile.footer ?? '',
      invoice_prefix: profile.invoice_prefix ?? 'F',
      credit_note_prefix: profile.credit_note_prefix ?? 'AV',
      proforma_prefix: profile.proforma_prefix ?? 'PF',
    });
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.setProfile(
        await this.api.updateBillingProfile(Number(this.editionId()), {
          ...value,
          vat_rate: value.vat_rate.trim() || null,
        }),
      );
      this.status.set(this.translate.instant('gestion.settings.saved'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }
}
