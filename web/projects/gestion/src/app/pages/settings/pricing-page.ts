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
import { FormGroup, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  Category,
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  Currency,
  DiscountKind,
  DiscountScope,
  ErrorSummary,
  FeeRequest,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  LanguageService,
  MeStore,
  Option,
  PageHeader,
  Period,
  PromoCode,
  RegistrationSettings,
  toDateTimeLocalValue,
  Zone,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { money, RegistrationsApi } from '../../core/registrations-api';
import { label, PERIODS, ZONES } from '../registrations/registrations-support';

export const CURRENCIES: readonly Currency[] = ['XOF', 'XAF', 'EUR', 'USD', 'GNF', 'CDF'];
const AMOUNT = /^\d{1,10}(\.\d{1,2})?$/;
const SLUG = /^[-a-zA-Z0-9_]+$/;
const COUNTRY = /^[A-Za-z]{2}$/;

/** Nom du champ d'une cellule de la grille des tarifs (`early_local`…). */
export function feeKey(period: Period, zone: Zone): string {
  return `${period}_${zone}`;
}

/** Cellules remplies de la grille ; une cellule vide : combinaison non proposée (J2). */
export function feeCells(value: Record<string, string>): FeeRequest[] {
  const cells: FeeRequest[] = [];
  for (const period of PERIODS) {
    for (const zone of ZONES) {
      const amount = (value[feeKey(period, zone)] ?? '').trim();
      if (amount) {
        cells.push({ period, zone, amount });
      }
    }
  }
  return cells;
}

/** « ci, SN ; bf » → `['CI', 'SN', 'BF']` (codes ISO 3166-1 alpha-2, contrôlés au serveur). */
export function parseCountries(text: string): string[] {
  return text
    .split(/[\s,;]+/)
    .map((code) => code.trim().toUpperCase())
    .filter(Boolean);
}

type Editing = number | null;

/**
 * Tarifs et paramètres des inscriptions (plan L6, J2, J4, J5, J9) : devise et moyens de
 * paiement proposés, pays « locaux », délais de paiement, conditions d'annulation (date
 * limite **saisie à l'heure de l'édition**, D13) ; catégories et leur grille (période ×
 * zone, cellule vide : non proposée), options à quota, codes promo. Lecture
 * `registrations.read`, écriture `pricing.write` ; le serveur contrôle les montants (décimales
 * de la devise) et refuse de supprimer ce qui est utilisé (il faut le désactiver).
 */
@Component({
  selector: 'gestion-pricing-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pricing-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 0 1.5rem;
    }
    fieldset {
      border: 0;
      margin: 0 0 0.75rem;
      padding: 0;
    }
    legend {
      font-weight: 600;
      margin-bottom: 0.25rem;
    }
  `,
})
export class PricingPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);

  protected readonly currencies = CURRENCIES;
  protected readonly periods = PERIODS;
  protected readonly zones = ZONES;
  protected readonly feeKey = feeKey;
  protected readonly settings = signal<RegistrationSettings | null>(null);
  protected readonly categories = signal<Category[]>([]);
  protected readonly options = signal<Option[]>([]);
  protected readonly promoCodes = signal<PromoCode[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** `null` : pas de formulaire ; `0` : création ; sinon : élément modifié. */
  protected readonly categoryEditing = signal<Editing>(null);
  protected readonly feesEditing = signal<Editing>(null);
  protected readonly optionEditing = signal<Editing>(null);
  protected readonly promoEditing = signal<Editing>(null);

  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('pricing.write'),
  );
  protected readonly currency = computed(() => this.settings()?.currency ?? 'XOF');

  protected readonly settingsForm = this.fb.group({
    currency: this.fb.control<Currency>('XOF'),
    online_enabled: [false],
    transfer_enabled: [true],
    onsite_enabled: [true],
    online_deadline_hours: [48, [Validators.required, Validators.min(1), Validators.max(720)]],
    transfer_deadline_days: [30, [Validators.required, Validators.min(1), Validators.max(180)]],
    local_countries: [''],
    cancellation_deadline_local: [''],
    refund_percent_before: [100, [Validators.required, Validators.min(0), Validators.max(100)]],
    refund_percent_after: [0, [Validators.required, Validators.min(0), Validators.max(100)]],
  });
  protected readonly categoryForm = this.fb.group({
    code: ['', [Validators.required, Validators.maxLength(32), Validators.pattern(SLUG)]],
    label_fr: ['', [Validators.required, Validators.maxLength(150)]],
    label_en: ['', Validators.maxLength(150)],
    description_fr: [''],
    description_en: [''],
    requires_proof: [false],
    is_active: [true],
    position: [0, [Validators.min(0), Validators.max(32767)]],
    // Bandeau du badge (plan L7, K3) : « #RRGGBB » ; vide, couleur par défaut selon l'ordre.
    badge_color: ['', Validators.pattern(/^#[0-9A-Fa-f]{6}$/)],
  });
  protected readonly feesForm: FormGroup = this.fb.group(
    Object.fromEntries(
      PERIODS.flatMap((period) =>
        ZONES.map((zone) => [feeKey(period, zone), ['', Validators.pattern(AMOUNT)]]),
      ),
    ),
  );
  protected readonly optionForm = this.fb.group({
    code: ['', [Validators.required, Validators.maxLength(32), Validators.pattern(SLUG)]],
    label_fr: ['', [Validators.required, Validators.maxLength(150)]],
    label_en: ['', Validators.maxLength(150)],
    description_fr: [''],
    description_en: [''],
    price_local: ['0', [Validators.required, Validators.pattern(AMOUNT)]],
    price_international: ['0', [Validators.required, Validators.pattern(AMOUNT)]],
    quota: [null as number | null, [Validators.min(0), Validators.max(1000000)]],
    categories: [[] as string[]],
    is_active: [true],
    position: [0, [Validators.min(0), Validators.max(32767)]],
  });
  protected readonly promoForm = this.fb.group({
    code: ['', [Validators.required, Validators.maxLength(32), Validators.pattern(SLUG)]],
    kind: this.fb.control<DiscountKind>('percent'),
    value: ['', [Validators.required, Validators.pattern(AMOUNT)]],
    scope: this.fb.control<DiscountScope>('registration'),
    categories: [[] as string[]],
    max_uses: [null as number | null, [Validators.min(1), Validators.max(1000000)]],
    valid_until_local: [''],
    is_active: [true],
  });

  async ngOnInit(): Promise<void> {
    const id = this.edition();
    try {
      const [edition, settings, categories, options, promoCodes] = await Promise.all([
        this.editions.edition(id),
        this.api.settings(id),
        this.api.categories(id),
        this.api.options(id),
        this.api.promoCodes(id),
      ]);
      this.timezone.set(edition.timezone);
      this.setSettings(settings);
      this.categories.set(categories);
      this.options.set(options);
      this.promoCodes.set(promoCodes);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
    if (!this.canWrite()) {
      this.settingsForm.disable();
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
  }

  protected amount(value: string | null | undefined): string {
    return money(value, this.currency(), this.language.current());
  }

  protected itemLabel(item: { label_fr: string; label_en?: string }): string {
    return label(item, this.language.current());
  }

  protected fee(category: Category, period: Period, zone: Zone): string {
    const found = category.fees.find((fee) => fee.period === period && fee.zone === zone);
    return found ? this.amount(found.amount) : '—';
  }

  protected error(form: FormGroup, name: string): string {
    const control = form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  // --- Paramètres ---------------------------------------------------------------------------

  private setSettings(settings: RegistrationSettings): void {
    this.settings.set(settings);
    this.settingsForm.reset({
      currency: settings.currency ?? 'XOF',
      online_enabled: settings.online_enabled ?? false,
      transfer_enabled: settings.transfer_enabled ?? true,
      onsite_enabled: settings.onsite_enabled ?? true,
      online_deadline_hours: settings.online_deadline_hours ?? 48,
      transfer_deadline_days: settings.transfer_deadline_days ?? 30,
      local_countries: (settings.local_countries ?? []).join(', '),
      cancellation_deadline_local: settings.cancellation_deadline_local
        ? toDateTimeLocalValue(settings.cancellation_deadline_local)
        : '',
      refund_percent_before: settings.refund_percent_before ?? 100,
      refund_percent_after: settings.refund_percent_after ?? 0,
    });
  }

  protected async saveSettings(): Promise<void> {
    if (!this.valid(this.settingsForm)) {
      return;
    }
    const countries = parseCountries(this.settingsForm.getRawValue().local_countries);
    if (countries.some((code) => !COUNTRY.test(code))) {
      const message = this.translate.instant('gestion.settings.pricing.countriesInvalid');
      const control = this.settingsForm.controls.local_countries;
      control.setErrors({ server: [message] });
      control.markAsTouched();
      this.errors.set([message]);
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const value = this.settingsForm.getRawValue();
    await this.run(this.settingsForm, async () => {
      this.setSettings(
        await this.api.updateSettings(this.edition(), {
          currency: value.currency,
          online_enabled: value.online_enabled,
          transfer_enabled: value.transfer_enabled,
          onsite_enabled: value.onsite_enabled,
          online_deadline_hours: Number(value.online_deadline_hours),
          transfer_deadline_days: Number(value.transfer_deadline_days),
          local_countries: countries,
          cancellation_deadline_local: value.cancellation_deadline_local || null,
          refund_percent_before: Number(value.refund_percent_before),
          refund_percent_after: Number(value.refund_percent_after),
        }),
      );
    });
  }

  // --- Catégories et grille -------------------------------------------------------------------

  protected startCategory(category?: Category): void {
    this.closeForms();
    this.categoryForm.reset({
      code: category?.code ?? '',
      label_fr: category?.label_fr ?? '',
      label_en: category?.label_en ?? '',
      description_fr: category?.description_fr ?? '',
      description_en: category?.description_en ?? '',
      requires_proof: category?.requires_proof ?? false,
      is_active: category?.is_active ?? true,
      position: category?.position ?? this.categories().length,
      badge_color: category?.badge_color ?? '',
    });
    if (category) {
      this.categoryForm.controls.code.disable();
    } else {
      this.categoryForm.controls.code.enable();
    }
    this.categoryEditing.set(category?.id ?? 0);
  }

  protected async saveCategory(): Promise<void> {
    if (!this.valid(this.categoryForm)) {
      return;
    }
    const id = this.categoryEditing();
    const { code, ...rest } = this.categoryForm.getRawValue();
    const saved = await this.run(this.categoryForm, async () => {
      if (id) {
        await this.api.updateCategory(this.edition(), id, rest);
      } else {
        await this.api.createCategory(this.edition(), { code, ...rest });
      }
      await this.refreshCatalog();
    });
    if (saved) {
      this.categoryEditing.set(null);
    }
  }

  protected startFees(category: Category): void {
    this.closeForms();
    const value: Record<string, string> = {};
    for (const period of PERIODS) {
      for (const zone of ZONES) {
        const found = category.fees.find((fee) => fee.period === period && fee.zone === zone);
        value[feeKey(period, zone)] = found?.amount ?? '';
      }
    }
    this.feesForm.reset(value);
    this.feesEditing.set(category.id);
  }

  protected async saveFees(): Promise<void> {
    const id = this.feesEditing();
    if (!id || !this.valid(this.feesForm)) {
      return;
    }
    const cells = feeCells(this.feesForm.getRawValue() as Record<string, string>);
    const saved = await this.run(this.feesForm, async () => {
      await this.api.setFees(this.edition(), id, cells);
      await this.refreshCatalog();
    });
    if (saved) {
      this.feesEditing.set(null);
    }
  }

  protected async removeCategory(category: Category): Promise<void> {
    if (!(await this.confirmDelete(category.label_fr))) {
      return;
    }
    await this.run(
      undefined,
      async () => {
        await this.api.deleteCategory(this.edition(), category.id);
        await this.refreshCatalog();
      },
      'gestion.settings.deleted',
    );
  }

  // --- Options ----------------------------------------------------------------------------------

  protected startOption(option?: Option): void {
    this.closeForms();
    this.optionForm.reset({
      code: option?.code ?? '',
      label_fr: option?.label_fr ?? '',
      label_en: option?.label_en ?? '',
      description_fr: option?.description_fr ?? '',
      description_en: option?.description_en ?? '',
      price_local: option?.price_local ?? '0',
      price_international: option?.price_international ?? '0',
      quota: option?.quota ?? null,
      categories: [...(option?.categories ?? [])],
      is_active: option?.is_active ?? true,
      position: option?.position ?? this.options().length,
    });
    this.optionEditing.set(option?.id ?? 0);
  }

  protected async saveOption(): Promise<void> {
    if (!this.valid(this.optionForm)) {
      return;
    }
    const id = this.optionEditing();
    const raw = this.optionForm.getRawValue();
    const body = {
      ...raw,
      quota: raw.quota === null || (raw.quota as unknown) === '' ? null : Number(raw.quota),
    };
    const saved = await this.run(this.optionForm, async () => {
      if (id) {
        await this.api.updateOption(this.edition(), id, body);
      } else {
        await this.api.createOption(this.edition(), body);
      }
      this.options.set(await this.api.options(this.edition()));
    });
    if (saved) {
      this.optionEditing.set(null);
    }
  }

  protected async removeOption(option: Option): Promise<void> {
    if (!(await this.confirmDelete(option.label_fr))) {
      return;
    }
    await this.run(
      undefined,
      async () => {
        await this.api.deleteOption(this.edition(), option.id);
        this.options.set(await this.api.options(this.edition()));
      },
      'gestion.settings.deleted',
    );
  }

  // --- Codes promo --------------------------------------------------------------------------------

  protected startPromo(promo?: PromoCode): void {
    this.closeForms();
    this.promoForm.reset({
      code: promo?.code ?? '',
      kind: promo?.kind ?? 'percent',
      value: promo?.value ?? '',
      scope: promo?.scope ?? 'registration',
      categories: [...(promo?.categories ?? [])],
      max_uses: promo?.max_uses ?? null,
      valid_until_local: promo?.valid_until_local
        ? toDateTimeLocalValue(promo.valid_until_local)
        : '',
      is_active: promo?.is_active ?? true,
    });
    this.promoEditing.set(promo?.id ?? 0);
  }

  protected async savePromo(): Promise<void> {
    if (!this.valid(this.promoForm)) {
      return;
    }
    const id = this.promoEditing();
    const raw = this.promoForm.getRawValue();
    const body = {
      ...raw,
      max_uses:
        raw.max_uses === null || (raw.max_uses as unknown) === '' ? null : Number(raw.max_uses),
      valid_until_local: raw.valid_until_local || null,
    };
    const saved = await this.run(this.promoForm, async () => {
      if (id) {
        await this.api.updatePromoCode(this.edition(), id, body);
      } else {
        await this.api.createPromoCode(this.edition(), body);
      }
      this.promoCodes.set(await this.api.promoCodes(this.edition()));
    });
    if (saved) {
      this.promoEditing.set(null);
    }
  }

  protected async removePromo(promo: PromoCode): Promise<void> {
    if (!(await this.confirmDelete(promo.code))) {
      return;
    }
    await this.run(
      undefined,
      async () => {
        await this.api.deletePromoCode(this.edition(), promo.id);
        this.promoCodes.set(await this.api.promoCodes(this.edition()));
      },
      'gestion.settings.deleted',
    );
  }

  protected promoValue(promo: PromoCode): string {
    return promo.kind === 'percent' ? `${Number(promo.value)} %` : this.amount(promo.value);
  }

  protected closeForms(): void {
    this.categoryEditing.set(null);
    this.feesEditing.set(null);
    this.optionEditing.set(null);
    this.promoEditing.set(null);
    this.errors.set([]);
  }

  // --- Outils -------------------------------------------------------------------------------------

  private async refreshCatalog(): Promise<void> {
    this.categories.set(await this.api.categories(this.edition()));
  }

  private valid(form: FormGroup): boolean {
    if (form.invalid) {
      form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return false;
    }
    return true;
  }

  private async confirmDelete(name: string): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.settings.deleteTitle'),
      message: this.translate.instant('gestion.settings.deleteMessage', { name }),
      confirmLabel: this.translate.instant('gestion.settings.delete'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return !!(await firstValueFrom(ref.afterClosed()));
  }

  /** Écriture : `true` si le serveur l'a acceptée ; erreurs de champ posées sur `form`. */
  private async run(
    form: FormGroup | undefined,
    action: () => Promise<void>,
    done = 'gestion.settings.saved',
  ): Promise<boolean> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
      this.status.set(this.translate.instant(done));
      return true;
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, form));
      focusFirstInvalid(this.host.nativeElement);
      return false;
    } finally {
      this.busy.set(false);
    }
  }
}
