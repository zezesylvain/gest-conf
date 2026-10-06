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
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  Category,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  LanguageService,
  ManageOrderRequest,
  ManageRegistrationList,
  MeStore,
  Option,
  OrderMethod,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import {
  money,
  RegistrationFilters,
  RegistrationsApi,
  saveBlob,
} from '../../core/registrations-api';
import {
  categoryLabel,
  label,
  ORDER_METHODS,
  PAYMENT_METHODS,
  REGISTRATION_STATUSES,
} from './registrations-support';

const PAGE_SIZE = 25;

/**
 * Inscriptions de l'édition (plan L6, J12) : liste filtrée (statut, catégorie, moyen de
 * paiement, recherche par nom, adresse ou référence) et paginée ; export CSV des mêmes
 * filtres (journalisé, réauthentification ouverte par l'intercepteur). Le CO « finances »
 * ou « secrétariat » saisit une inscription pour un compte existant (`registrations.manage`,
 * J1) ; le serveur applique les mêmes règles que pour le participant (quotas, codes promo,
 * période tarifaire, sur place après la clôture).
 */
@Component({
  selector: 'gestion-registrations-page',
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
  templateUrl: './registrations-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
  `,
})
export class RegistrationsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(RegistrationsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = REGISTRATION_STATUSES;
  protected readonly methods = PAYMENT_METHODS;
  protected readonly orderMethods = ORDER_METHODS;
  protected readonly rows = signal<ManageRegistrationList[]>([]);
  protected readonly categories = signal<Category[]>([]);
  protected readonly options = signal<Option[]>([]);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly creating = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly canManage = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('registrations.manage'),
  );
  protected readonly activeCategories = computed(() =>
    this.categories().filter((category) => category.is_active !== false),
  );
  protected readonly activeOptions = computed(() =>
    this.options().filter((option) => option.is_active !== false),
  );

  protected readonly form = this.fb.group({
    q: [''],
    status: [''],
    category: [''],
    method: [''],
  });
  protected readonly orderForm = this.fb.group({
    email: ['', [Validators.required, Validators.email, Validators.maxLength(254)]],
    category: ['', Validators.required],
    method: this.fb.control<OrderMethod>('transfer'),
    options: [[] as string[]],
    promo_code: ['', Validators.maxLength(32)],
    billing_name: ['', Validators.maxLength(255)],
    billing_organization: ['', Validators.maxLength(255)],
    billing_address: ['', Validators.maxLength(2000)],
  });

  async ngOnInit(): Promise<void> {
    const id = this.edition();
    try {
      const [edition, categories, options] = await Promise.all([
        this.editions.edition(id),
        this.api.categories(id),
        this.api.options(id),
      ]);
      this.timezone.set(edition.timezone);
      this.categories.set(categories);
      this.options.set(options);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    await this.reload();
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
  }

  protected amount(value: string, currency: string): string {
    return money(value, currency, this.language.current());
  }

  protected categoryName(row: ManageRegistrationList): string {
    return categoryLabel(row.category, this.language.current());
  }

  protected itemLabel(item: { label_fr: string; label_en?: string }): string {
    return label(item, this.language.current());
  }

  protected error(name: string): string {
    const control = this.orderForm.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected async search(): Promise<void> {
    this.page.set(1);
    await this.reload();
  }

  protected async reset(): Promise<void> {
    this.form.reset();
    await this.search();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  protected async exportCsv(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      const blob = await this.api.exportRegistrations(this.edition(), this.currentFilters());
      saveBlob(blob, `inscriptions-${this.editionId()}.csv`);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected startCreate(): void {
    this.orderForm.reset();
    this.errors.set([]);
    this.creating.set(true);
  }

  protected async create(): Promise<void> {
    if (this.orderForm.invalid) {
      this.orderForm.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const value = this.orderForm.getRawValue();
    const body: ManageOrderRequest = {
      email: value.email.trim(),
      category: value.category,
      method: value.method,
      options: value.options,
      billing_name: value.billing_name.trim(),
      billing_organization: value.billing_organization.trim(),
      billing_address: value.billing_address.trim(),
    };
    if (value.promo_code.trim()) {
      body.promo_code = value.promo_code.trim();
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      const created = await this.api.create(this.edition(), body);
      await this.router.navigate(['/editions', this.editionId(), 'inscriptions', created.id]);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.orderForm));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }

  /** Filtres non vides du formulaire, tels que les attend l'API (et l'export). */
  private currentFilters(): RegistrationFilters {
    const value = this.form.getRawValue();
    const filters: RegistrationFilters = {};
    if (value.q.trim()) filters.q = value.q.trim();
    if (value.status) filters.status = value.status;
    if (value.category) filters.category = value.category;
    if (value.method) filters.method = value.method;
    return filters;
  }

  private async reload(): Promise<void> {
    this.errors.set([]);
    try {
      const result = await this.api.list(this.edition(), {
        ...this.currentFilters(),
        page: this.page(),
        page_size: PAGE_SIZE,
      });
      this.rows.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }
}
