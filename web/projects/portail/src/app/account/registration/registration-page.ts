import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  ElementRef,
  inject,
  Injectable,
  OnInit,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { FormGroup, NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyServerErrors,
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  formatMoney,
  GcApiError,
  LanguageService,
  MeStore,
  MyRegistration,
  OrderMethod,
  PageHeader,
  PublicOption,
  PublicRegistration,
  Quote,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { RegistrationData } from '../../site/registration/registration-data';
import { inLanguage } from '../../site/registration/registration-support';
import { documentUrl, isActive, qrUrl, RegistrationService } from './registration.service';

/** Moyens qu'une commande peut choisir ; `free` et `waiver` ne se choisissent pas. */
const ORDER_METHODS: readonly OrderMethod[] = ['online', 'transfer', 'onsite'];

/**
 * Redirection vers la page de paiement hébergée par le fournisseur : le navigateur y est
 * **dirigé**, jamais par un formulaire (CSP du portail, bilan de L6.0). Isolée pour les tests.
 */
@Injectable({ providedIn: 'root' })
export class PaymentRedirect {
  private readonly document = inject(DOCUMENT);

  go(url: string): void {
    this.document.defaultView?.location.assign(url);
  }
}

/**
 * « Mon inscription » (plan L6, J13) : commande (catégorie, options, code promo, moyen de
 * paiement, facturation) avec prix calculé par le serveur, puis suivi : statut, échéance,
 * paiement en ligne, pro forma, justificatif, factures, QR d'accès, annulation. Au retour de
 * la page de paiement (`?paiement=`), le fournisseur est interrogé : le retour seul ne
 * prouve rien (RG-15).
 */
@Component({
  selector: 'portail-registration-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
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
  templateUrl: './registration-page.html',
  styleUrl: './registration-page.scss',
})
export class RegistrationPage implements OnInit {
  private readonly service = inject(RegistrationService);
  private readonly data = inject(RegistrationData);
  private readonly redirect = inject(PaymentRedirect);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);
  protected readonly meStore = inject(MeStore);

  protected readonly catalog = signal<PublicRegistration | null>(null);
  protected readonly registrations = signal<MyRegistration[]>([]);
  protected readonly quote = signal<Quote | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal('');
  protected readonly editingBilling = signal(false);

  /** Inscription en cours (une seule par édition) et inscriptions closes. */
  protected readonly active = computed(() => this.registrations().find(isActive) ?? null);
  protected readonly past = computed(() => this.registrations().filter((item) => !isActive(item)));
  protected readonly methods = computed(() =>
    ORDER_METHODS.filter((method) => this.catalog()?.methods.includes(method)),
  );

  protected readonly orderForm = this.fb.group({
    category: ['', Validators.required],
    options: [[] as string[]],
    promo_code: ['', Validators.maxLength(32)],
    method: this.fb.control<OrderMethod | ''>('', Validators.required),
    billing_name: ['', Validators.maxLength(255)],
    billing_organization: ['', Validators.maxLength(255)],
    billing_address: ['', Validators.maxLength(2000)],
  });
  protected readonly billingForm = this.fb.group({
    billing_name: ['', Validators.maxLength(255)],
    billing_organization: ['', Validators.maxLength(255)],
    billing_address: ['', Validators.maxLength(2000)],
  });

  private readonly category = toSignal(this.orderForm.controls.category.valueChanges, {
    initialValue: '',
  });
  /** Options proposées à la catégorie choisie (vide : réservée à aucune). */
  protected readonly options = computed(() => {
    const category = this.category();
    return (this.catalog()?.options ?? []).filter(
      (option) => !option.categories.length || option.categories.includes(category),
    );
  });
  protected readonly selectedCategory = computed(
    () => this.catalog()?.categories.find((item) => item.code === this.category()) ?? null,
  );

  async ngOnInit(): Promise<void> {
    try {
      const [registrations, catalog] = await Promise.all([
        this.service.list(),
        this.data.catalog().catch((error: unknown) => {
          // Pas d'édition ouverte aux inscriptions : suivi des inscriptions passées seul.
          if (error instanceof GcApiError && error.status === 404) {
            return null;
          }
          throw error;
        }),
      ]);
      this.registrations.set(registrations);
      this.catalog.set(catalog);
      const methods = this.methods();
      if (methods.length === 1) {
        this.orderForm.controls.method.setValue(methods[0]);
      }
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
    await this.afterPayment();
  }

  // --- Affichage ----------------------------------------------------------------------------

  protected text(item: { label_fr: string; label_en?: string }): string {
    return inLanguage(item.label_fr, item.label_en, this.language.current());
  }

  protected description(item: { description_fr: string; description_en: string }): string {
    return inLanguage(item.description_fr, item.description_en, this.language.current());
  }

  protected title(registration: MyRegistration): string {
    return inLanguage(
      registration.edition.title_fr,
      registration.edition.title_en,
      this.language.current(),
    );
  }

  protected amount(value: string | null | undefined, currency: string): string {
    return formatMoney(value, currency, this.language.current());
  }

  protected date(value: string | null | undefined, timezone: string): string {
    return value ? formatInZone(value, timezone, this.language.current()) : '—';
  }

  protected optionPrice(option: PublicOption): string {
    const currency = this.catalog()?.currency ?? 'XOF';
    return `${this.amount(option.price_local, currency)} / ${this.amount(option.price_international, currency)}`;
  }

  protected documentHref(registration: MyRegistration, id: number): string {
    return documentUrl(registration.id, id);
  }

  protected qrSrc(registration: MyRegistration): string {
    return qrUrl(registration.id);
  }

  protected error(form: FormGroup, name: string): string {
    const control = form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected owes(registration: MyRegistration): boolean {
    return Number(registration.total) > 0;
  }

  /** Identité de facturation modifiable jusqu'à l'émission de la facture. */
  protected canEditBilling(registration: MyRegistration): boolean {
    return (
      isActive(registration) &&
      !registration.documents.some((document) => document.kind === 'invoice')
    );
  }

  protected quoteCaption(price: Quote): string {
    return this.translate.instant('portail.registration.account.quoteTitle', {
      period: this.translate.instant(`portail.registration.period.${price.period}`),
      zone: this.translate.instant(`portail.registration.zone.${price.zone}`),
    });
  }

  /** Paiement en ligne possible : en attente, montant dû, moyen proposé par l'édition. */
  protected canPayOnline(registration: MyRegistration): boolean {
    return (
      registration.status === 'pending' &&
      Number(registration.total) > 0 &&
      !!this.catalog()?.methods.includes('online')
    );
  }

  /** Options dépendantes de la catégorie : un changement de catégorie les réinitialise. */
  protected categoryChanged(): void {
    this.orderForm.controls.options.setValue([]);
    this.quote.set(null);
  }

  protected toggleOption(code: string, checked: boolean): void {
    const current = this.orderForm.controls.options.value.filter((item) => item !== code);
    this.orderForm.controls.options.setValue(checked ? [...current, code] : current);
    this.quote.set(null);
  }

  // --- Commande -----------------------------------------------------------------------------

  /** Prix calculé par le serveur, sans engagement (aucune place ni code réservés). */
  protected async computeQuote(): Promise<void> {
    if (!this.valid(this.orderForm, ['category'])) {
      return;
    }
    const value = this.orderForm.getRawValue();
    await this.run(async () => {
      this.quote.set(
        await this.service.quote({
          category: value.category,
          options: value.options,
          promo_code: value.promo_code.trim(),
        }),
      );
    }, this.orderForm);
  }

  protected async placeOrder(): Promise<void> {
    if (!this.valid(this.orderForm)) {
      return;
    }
    const value = this.orderForm.getRawValue();
    await this.run(async () => {
      const created = await this.service.order({
        category: value.category,
        options: value.options,
        promo_code: value.promo_code.trim(),
        method: value.method as OrderMethod,
        billing_name: value.billing_name.trim(),
        billing_organization: value.billing_organization.trim(),
        billing_address: value.billing_address.trim(),
      });
      this.registrations.update((items) => [created, ...items]);
      this.quote.set(null);
      this.notice.set(this.translate.instant('portail.registration.account.ordered'));
      if (created.method === 'online' && this.canPayOnline(created)) {
        await this.startPayment(created);
      }
    }, this.orderForm);
  }

  // --- Suivi --------------------------------------------------------------------------------

  protected async pay(registration: MyRegistration): Promise<void> {
    await this.run(() => this.startPayment(registration));
  }

  private async startPayment(registration: MyRegistration): Promise<void> {
    const start = await this.service.pay(registration.id);
    this.redirect.go(start.payment_url);
  }

  protected async requestProforma(registration: MyRegistration): Promise<void> {
    await this.run(async () => {
      await this.service.proforma(registration.id);
      this.replace(await this.service.get(registration.id));
      this.notice.set(this.translate.instant('portail.registration.account.proformaIssued'));
    });
  }

  protected async uploadProof(registration: MyRegistration, event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    await this.run(async () => {
      this.replace(await this.service.uploadProof(registration.id, file));
      this.notice.set(this.translate.instant('portail.registration.account.proofSaved'));
    });
    input.value = '';
  }

  protected startBilling(registration: MyRegistration): void {
    this.billingForm.reset({
      billing_name: registration.billing_name,
      billing_organization: registration.billing_organization,
      billing_address: registration.billing_address,
    });
    this.editingBilling.set(true);
  }

  protected async saveBilling(registration: MyRegistration): Promise<void> {
    if (!this.valid(this.billingForm)) {
      return;
    }
    const value = this.billingForm.getRawValue();
    await this.run(async () => {
      this.replace(
        await this.service.updateBilling(registration.id, {
          billing_name: value.billing_name.trim(),
          billing_organization: value.billing_organization.trim(),
          billing_address: value.billing_address.trim(),
        }),
      );
      this.editingBilling.set(false);
      this.notice.set(this.translate.instant('portail.registration.account.billingSaved'));
    }, this.billingForm);
  }

  protected async cancel(registration: MyRegistration): Promise<void> {
    const key =
      registration.status === 'confirmed'
        ? 'portail.registration.account.cancelConfirmed'
        : 'portail.registration.account.cancelPending';
    const data: ConfirmDialogData = {
      title: this.translate.instant(`${key}.title`),
      message: this.translate.instant(`${key}.message`, {
        percent: registration.refund_percent ?? 0,
      }),
      confirmLabel: this.translate.instant(`${key}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    if (!(await firstValueFrom(ref.afterClosed()))) {
      return;
    }
    await this.run(async () => {
      this.replace(await this.service.cancel(registration.id));
      this.notice.set(this.translate.instant('portail.registration.account.cancelled'));
    });
  }

  /**
   * Retour de la page de paiement (`?paiement=<référence>`, `&echec=1` si abandon) : le
   * fournisseur est interrogé (RG-15), puis l'adresse est nettoyée.
   */
  private async afterPayment(): Promise<void> {
    const params = this.route.snapshot.queryParamMap;
    const reference = params.get('paiement');
    const registration = this.active();
    if (!reference) {
      return;
    }
    if (registration?.status === 'pending') {
      try {
        const check = await this.service.paymentCheck(registration.id);
        this.replace(await this.service.get(registration.id));
        const outcome =
          check.status === 'confirmed'
            ? 'confirmed'
            : check.outcome === 'failed' || params.get('echec')
              ? 'failed'
              : 'pending';
        this.notice.set(this.translate.instant(`portail.registration.account.payment.${outcome}`));
      } catch (error) {
        this.errors.set([apiErrorMessage(this.translate, error)]);
      }
    } else if (registration?.status === 'confirmed') {
      this.notice.set(this.translate.instant('portail.registration.account.payment.confirmed'));
    }
    await this.router.navigate([], { relativeTo: this.route, queryParams: {}, replaceUrl: true });
  }

  // --- Outils -------------------------------------------------------------------------------

  private replace(updated: MyRegistration): void {
    this.registrations.update((items) =>
      items.map((item) => (item.id === updated.id ? updated : item)),
    );
  }

  /** Formulaire valide (ou seulement les champs nommés) ; sinon champs signalés. */
  private valid(form: FormGroup, names?: string[]): boolean {
    const controls = names ? names.map((name) => form.get(name)!) : [form];
    if (controls.some((control) => control.invalid)) {
      controls.forEach((control) => control.markAllAsTouched());
      focusFirstInvalid(this.host.nativeElement);
      return false;
    }
    return true;
  }

  /**
   * Messages d'une erreur : erreurs de champ posées sur le formulaire ; pour un refus de
   * règle (409 : quota atteint, profil incomplet…), le message du serveur, qui dit ce qui
   * bloque.
   */
  private messages(error: unknown, form?: FormGroup): string[] {
    if (!(error instanceof GcApiError)) {
      return [apiErrorMessage(this.translate, error)];
    }
    const unplaced =
      form && Object.keys(error.fields).length ? applyServerErrors(form, error) : null;
    if (error.status === 409 && error.message) {
      return [error.message, ...(unplaced ?? [])];
    }
    return unplaced ?? [apiErrorMessage(this.translate, error)];
  }

  private async run(action: () => Promise<void>, form?: FormGroup): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.notice.set('');
    try {
      await action();
    } catch (error) {
      this.errors.set(this.messages(error, form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }
}
