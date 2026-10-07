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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  MeStore,
  PageHeader,
  SponsorBenefit,
  SponsorDetail,
  SponsorLevel,
  SponsorStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { SponsorsApi } from '../../core/sponsors-api';
import { confirmAction } from '../events/events-support';
import { formatDay } from '../organisation/organisation-support';
import { levelName, LOGO_ACCEPT, LOGO_MAX_BYTES, SPONSOR_STATUSES } from './sponsors-support';

/** Date du jour du navigateur (`AAAA-MM-JJ`), pour une contrepartie livrée aujourd'hui. */
function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/**
 * Fiche d'un partenaire (plan L8, N5) : partie **publique** (nom, niveau, site,
 * présentations, logo, publication) et partie **privée** (contact, statut, contribution
 * convenue et reçue, note interne), contreparties cochées à leur livraison. Écriture
 * `sponsors.write` ; « contribution reçue » exige montant et date (revérifié au serveur).
 */
@Component({
  selector: 'gestion-sponsor-detail-page',
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
  templateUrl: './sponsor-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .logo {
      max-width: 12rem;
      max-height: 6rem;
      object-fit: contain;
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.5rem;
      background: #fff;
    }
    .benefits li {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.25rem 0.75rem;
      padding: 0.25rem 0;
    }
  `,
})
export class SponsorDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly sponsorId = input.required<string>();

  private readonly api = inject(SponsorsApi);
  private readonly dialog = inject(MatDialog);
  private readonly meStore = inject(MeStore);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = SPONSOR_STATUSES;
  protected readonly accept = LOGO_ACCEPT;
  protected readonly sponsor = signal<SponsorDetail | null>(null);
  protected readonly levels = signal<SponsorLevel[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('sponsors.write'),
  );

  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly form = this.fb.group({
    name: ['', [Validators.required, Validators.maxLength(150)]],
    level: [null as number | null],
    website: ['', Validators.maxLength(300)],
    description_fr: ['', Validators.maxLength(1000)],
    description_en: ['', Validators.maxLength(1000)],
    published: [false],
    contact_name: ['', Validators.maxLength(150)],
    contact_email: ['', [Validators.email, Validators.maxLength(254)]],
    contact_phone: ['', Validators.maxLength(40)],
    status: ['prospect' as SponsorStatus],
    agreed_amount: [''],
    received_amount: [''],
    received_on: [''],
    note: ['', Validators.maxLength(2000)],
  });
  protected readonly benefitForm = this.fb.group({
    label: ['', [Validators.required, Validators.maxLength(200)]],
  });

  async ngOnInit(): Promise<void> {
    const edition = this.edition();
    try {
      const [sponsor, levels] = await Promise.all([
        this.api.sponsor(edition, this.id()),
        this.api.levels(edition),
      ]);
      this.levels.set(levels);
      this.show(sponsor);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  private id(): number {
    return Number(this.sponsorId());
  }

  protected levelOption(level: SponsorLevel): string {
    return levelName(level, this.language.current());
  }

  protected day(value: string | null): string {
    return formatDay(value, this.language.current());
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    await this.run('gestion.sponsors.detail.saved', () =>
      this.api.update(this.edition(), this.id(), {
        ...value,
        name: value.name.trim(),
        agreed_amount: value.agreed_amount === '' ? null : value.agreed_amount,
        received_amount: value.received_amount === '' ? null : value.received_amount,
        received_on: value.received_on || null,
      }),
    );
  }

  protected async uploadLogo(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (file.size > LOGO_MAX_BYTES) {
      this.errors.set([this.translate.instant('gestion.sponsors.detail.logoTooLarge')]);
      return;
    }
    await this.run('gestion.sponsors.detail.logoSaved', () =>
      this.api.uploadLogo(this.edition(), this.id(), file),
    );
  }

  protected async removeLogo(): Promise<void> {
    await this.run('gestion.sponsors.detail.logoRemoved', () =>
      this.api.removeLogo(this.edition(), this.id()),
    );
  }

  protected async addBenefit(): Promise<void> {
    if (this.benefitForm.invalid) {
      this.benefitForm.markAllAsTouched();
      return;
    }
    const label = this.benefitForm.getRawValue().label.trim();
    await this.run('gestion.sponsors.detail.benefitAdded', async () => {
      const sponsor = await this.api.addBenefit(this.edition(), this.id(), label);
      this.benefitForm.reset();
      return sponsor;
    });
  }

  protected async toggleBenefit(benefit: SponsorBenefit, delivered: boolean): Promise<void> {
    await this.run('gestion.sponsors.detail.benefitUpdated', () =>
      this.api.markBenefit(this.edition(), this.id(), benefit.id, delivered ? today() : null),
    );
  }

  protected async removeBenefit(benefit: SponsorBenefit): Promise<void> {
    await this.run('gestion.sponsors.detail.benefitRemoved', () =>
      this.api.removeBenefit(this.edition(), this.id(), benefit.id),
    );
  }

  protected async remove(): Promise<void> {
    const sponsor = this.sponsor();
    if (!sponsor) return;
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.sponsors.delete', {
      name: sponsor.name,
    });
    if (!answer) return;
    this.busy.set(true);
    this.errors.set([]);
    try {
      await this.api.remove(this.edition(), sponsor.id);
      await this.router.navigate(['/editions', this.editionId(), 'partenaires']);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async run(message: string, action: () => Promise<SponsorDetail>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.show(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private show(sponsor: SponsorDetail): void {
    this.sponsor.set(sponsor);
    this.form.reset({
      name: sponsor.name,
      level: sponsor.level,
      website: sponsor.website,
      description_fr: sponsor.description_fr,
      description_en: sponsor.description_en,
      published: sponsor.published,
      contact_name: sponsor.contact_name,
      contact_email: sponsor.contact_email,
      contact_phone: sponsor.contact_phone,
      status: sponsor.status,
      agreed_amount: sponsor.agreed_amount ?? '',
      received_amount: sponsor.received_amount ?? '',
      received_on: sponsor.received_on ?? '',
      note: sponsor.note,
    });
    if (this.canWrite()) {
      this.form.enable();
    } else {
      this.form.disable();
    }
  }
}
