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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  LanguageService,
  ManageRegistration,
  ManualPaymentMethod,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { documentUrl, money, proofUrl, RegistrationsApi } from '../../core/registrations-api';
import { categoryLabel, label, today } from './registrations-support';

/** Action du CO en cours de saisie (un seul formulaire ouvert à la fois). */
export type RegistrationAction = 'payment' | 'waive' | 'cancel' | 'refund';

const AMOUNT = /^\d{1,10}(\.\d{1,2})?$/;

/**
 * Détail d'une inscription (plan L6, J12) : lignes figées à la commande, justificatif,
 * mentions de facturation, pièces (PDF par endpoint authentifié, règle n° 8), paiements,
 * remboursements et historique. Actions du CO (`registrations.manage`, J1) : paiement reçu
 * hors ligne (J7, montant égal au total), gratuité (J4), pro forma, annulation motivée avec
 * part remboursée (J9), remboursement fait hors plateforme (avoir sur la facture).
 * Paiement manuel et remboursement demandent une réauthentification récente, ouverte par
 * l'intercepteur ; chaque action est revérifiée par le serveur (règle n° 2).
 */
@Component({
  selector: 'gestion-registration-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './registration-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
    dl {
      display: grid;
      grid-template-columns: minmax(0, max-content) minmax(0, 1fr);
      gap: 0.25rem 1rem;
      margin: 0;
    }
    dt {
      font-weight: 600;
    }
    dd {
      margin: 0;
      min-width: 0;
      overflow-wrap: anywhere;
    }
    /* Écran étroit (375 px) : libellé au-dessus de la valeur. */
    @media (max-width: 40rem) {
      dl {
        grid-template-columns: minmax(0, 1fr);
      }
      dd {
        margin-bottom: 0.5rem;
      }
    }
    .address {
      white-space: pre-wrap;
    }
  `,
})
export class RegistrationDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly registrationId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly events = inject(EventsApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);

  protected readonly detail = signal<ManageRegistration | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly action = signal<RegistrationAction | null>(null);

  protected readonly canManage = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('registrations.manage'),
  );
  /** Badge perdu : nouveau jeton, l'ancien badge refusé à l'accueil (plan L7, K2). */
  protected readonly canReplaceBadge = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('checkin.manage'),
  );
  protected readonly badgeUrl = computed(() =>
    eventsUrls.badge(this.editionId(), Number(this.registrationId())),
  );
  protected readonly pending = computed(() => this.detail()?.status === 'pending');
  protected readonly payable = computed(
    () => this.pending() && Number(this.detail()?.total ?? 0) > 0,
  );
  protected readonly cancellable = computed(() =>
    ['pending', 'confirmed'].includes(this.detail()?.status ?? ''),
  );
  protected readonly invoiced = computed(
    () => this.detail()?.documents.some((document) => document.kind === 'invoice') ?? false,
  );
  protected readonly refundable = computed(
    () => this.detail()?.status === 'cancelled' && this.invoiced(),
  );
  /** Reste à rembourser : part due à l'annulation moins les remboursements saisis. */
  protected readonly refundLeft = computed(() => {
    const detail = this.detail();
    if (!detail?.refund_due) {
      return null;
    }
    const done = detail.refunds.reduce((sum, refund) => sum + Number(refund.amount), 0);
    return Math.max(0, Number(detail.refund_due) - done);
  });

  protected readonly paymentForm = this.fb.group({
    method: this.fb.control<ManualPaymentMethod>('transfer'),
    amount: ['', [Validators.required, Validators.pattern(AMOUNT)]],
    received_on: ['', Validators.required],
    reference: ['', Validators.maxLength(64)],
    note: ['', Validators.maxLength(255)],
  });
  protected readonly reasonForm = this.fb.group({
    reason: ['', [Validators.required, Validators.maxLength(2000)]],
  });
  protected readonly cancelForm = this.fb.group({
    reason: ['', [Validators.required, Validators.maxLength(2000)]],
    refund_percent: [null as number | null, [Validators.min(0), Validators.max(100)]],
  });
  protected readonly refundForm = this.fb.group({
    amount: ['', [Validators.required, Validators.pattern(AMOUNT)]],
    method: ['', [Validators.required, Validators.maxLength(64)]],
    reference: ['', Validators.maxLength(64)],
    refunded_on: ['', Validators.required],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.detail.set(await this.api.get(this.edition(), this.registration()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  private registration(): number {
    return Number(this.registrationId());
  }

  protected date(value: string | null | undefined): string {
    return value
      ? formatInZone(value, this.detail()?.edition.timezone, this.language.current())
      : '—';
  }

  protected amount(value: string | number | null | undefined): string {
    return money(value, this.detail()?.currency ?? 'XOF', this.language.current());
  }

  protected itemLabel(item: { label_fr: string; label_en?: string }): string {
    return label(item, this.language.current());
  }

  protected category(detail: ManageRegistration): string {
    return categoryLabel(detail.category, this.language.current());
  }

  protected documentHref(id: number): string {
    return documentUrl(this.editionId(), this.registration(), id);
  }

  protected proofHref(): string {
    return proofUrl(this.editionId(), this.registration());
  }

  protected error(form: FormGroup, name: string): string {
    const control = form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected open(action: RegistrationAction): void {
    const detail = this.detail();
    this.errors.set([]);
    this.status.set('');
    if (action === 'payment') {
      this.paymentForm.reset({
        method: detail?.method === 'onsite' ? 'onsite' : 'transfer',
        amount: detail?.total ?? '',
        received_on: today(),
        reference: '',
        note: '',
      });
    } else if (action === 'waive') {
      this.reasonForm.reset();
    } else if (action === 'cancel') {
      this.cancelForm.reset({ reason: '', refund_percent: null });
    } else {
      const left = this.refundLeft();
      this.refundForm.reset({
        amount: left === null ? '' : left.toFixed(2),
        method: '',
        reference: '',
        refunded_on: today(),
      });
    }
    this.action.set(action);
  }

  protected close(): void {
    this.action.set(null);
  }

  protected async recordPayment(): Promise<void> {
    if (!this.valid(this.paymentForm)) {
      return;
    }
    const value = this.paymentForm.getRawValue();
    await this.run('gestion.registrations.detail.payment.done', this.paymentForm, () =>
      this.api.recordPayment(this.edition(), this.registration(), {
        method: value.method,
        amount: value.amount,
        received_on: value.received_on,
        reference: value.reference.trim(),
        note: value.note.trim(),
      }),
    );
  }

  protected async waive(): Promise<void> {
    if (!this.valid(this.reasonForm)) {
      return;
    }
    await this.run('gestion.registrations.detail.waive.done', this.reasonForm, () =>
      this.api.waive(this.edition(), this.registration(), {
        reason: this.reasonForm.getRawValue().reason.trim(),
      }),
    );
  }

  protected async cancel(): Promise<void> {
    if (!this.valid(this.cancelForm)) {
      return;
    }
    if (!(await this.confirm('gestion.registrations.detail.cancel'))) {
      return;
    }
    const value = this.cancelForm.getRawValue();
    const percent =
      value.refund_percent === null || (value.refund_percent as unknown) === ''
        ? null
        : Number(value.refund_percent);
    await this.run('gestion.registrations.detail.cancel.done', this.cancelForm, () =>
      this.api.cancel(this.edition(), this.registration(), {
        reason: value.reason.trim(),
        refund_percent: percent,
      }),
    );
  }

  protected async recordRefund(): Promise<void> {
    if (!this.valid(this.refundForm)) {
      return;
    }
    const value = this.refundForm.getRawValue();
    await this.run('gestion.registrations.detail.refund.done', this.refundForm, () =>
      this.api.recordRefund(this.edition(), this.registration(), {
        amount: value.amount,
        method: value.method.trim(),
        reference: value.reference.trim(),
        refunded_on: value.refunded_on,
      }),
    );
  }

  protected async issueProforma(): Promise<void> {
    await this.run('gestion.registrations.detail.proforma.done', undefined, () =>
      this.api.issueProforma(this.edition(), this.registration()),
    );
  }

  protected async replaceBadge(): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.registrations.detail.badge.replace.title'),
      message: this.translate.instant('gestion.registrations.detail.badge.replace.message'),
      confirmLabel: this.translate.instant('gestion.registrations.detail.badge.replace.confirm'),
      reasonLabel: this.translate.instant('gestion.registrations.detail.badge.replace.reason'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    const answer = await firstValueFrom(ref.afterClosed());
    if (!answer) {
      return;
    }
    await this.run('gestion.registrations.detail.badge.replace.done', undefined, async () => {
      await this.events.regenerateBadge(this.edition(), this.registration(), answer.reason.trim());
      return this.api.get(this.edition(), this.registration());
    });
  }

  private valid(form: FormGroup): boolean {
    if (form.invalid) {
      form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return false;
    }
    return true;
  }

  private async confirm(key: string): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant(`${key}.title`),
      message: this.translate.instant(`${key}.message`),
      confirmLabel: this.translate.instant(`${key}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return !!(await firstValueFrom(ref.afterClosed()));
  }

  private async run(
    done: string,
    form: FormGroup | undefined,
    action: () => Promise<ManageRegistration>,
  ): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.detail.set(await action());
      this.action.set(null);
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }
}
