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
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  Category,
  countryOptions,
  CounterResponse,
  ErrorSummary,
  LanguageService,
  Option,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { money, RegistrationsApi } from '../../core/registrations-api';
import { label } from '../registrations/registrations-support';

/**
 * Inscription au comptoir (plan L7, K13) d'une personne sans compte : compte créé sans mot
 * de passe (adresse non vérifiée, un lien de définition lui est envoyé), ou rattachement au
 * compte existant ; tarif « sur place » ; paiement reçu enregistré si coché ; badge à
 * imprimer aussitôt. `registrations.manage`, revérifié par le serveur.
 */
@Component({
  selector: 'gestion-counter-page',
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
  templateUrl: './counter-page.html',
  styleUrl: '../page.scss',
})
export class CounterPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly registrations = inject(RegistrationsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly categories = signal<Category[]>([]);
  protected readonly options = signal<Option[]>([]);
  protected readonly created = signal<CounterResponse | null>(null);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly countries = computed(() => countryOptions(this.language.current()));
  protected readonly form = inject(NonNullableFormBuilder).group({
    email: ['', [Validators.required, Validators.email, Validators.maxLength(254)]],
    first_name: ['', [Validators.required, Validators.maxLength(150)]],
    last_name: ['', [Validators.required, Validators.maxLength(150)]],
    institution: ['', Validators.maxLength(255)],
    country: [''],
    category: ['', Validators.required],
    options: [[] as string[]],
    paid: [true],
  });

  async ngOnInit(): Promise<void> {
    const id = Number(this.editionId());
    try {
      const [categories, options] = await Promise.all([
        this.registrations.categories(id),
        this.registrations.options(id),
      ]);
      this.categories.set(categories.filter((item) => item.is_active));
      this.options.set(options.filter((item) => item.is_active));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  protected label(item: { label_fr: string; label_en?: string }): string {
    return label(item, this.language.current());
  }

  protected total(response: CounterResponse): string {
    return money(response.total, response.currency, this.language.current());
  }

  protected badgeUrl(response: CounterResponse): string {
    return eventsUrls.badge(this.editionId(), response.registration_id);
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      const value = this.form.getRawValue();
      this.created.set(
        await this.api.counter(Number(this.editionId()), {
          ...value,
          email: value.email.trim(),
          first_name: value.first_name.trim(),
          last_name: value.last_name.trim(),
          institution: value.institution.trim(),
        }),
      );
      this.form.reset();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  protected another(): void {
    this.created.set(null);
  }
}
