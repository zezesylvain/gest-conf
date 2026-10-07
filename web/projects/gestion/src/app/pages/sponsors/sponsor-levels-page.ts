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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  LogoSize,
  MeStore,
  PageHeader,
  SponsorLevel,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { money } from '../../core/registrations-api';
import { SponsorsApi } from '../../core/sponsors-api';
import { confirmAction } from '../events/events-support';
import { levelName, LOGO_SIZES } from './sponsors-support';

/**
 * Niveaux de partenariat (plan L8, N5 ; `sponsors.read`, écriture `sponsors.write`) :
 * noms FR et EN, montant indicatif, contreparties (une par ligne, recopiées sur la fiche
 * d'un partenaire à l'attribution du niveau), taille du logo au portail. Un niveau attribué
 * ne se supprime pas (refus du serveur, `in_use`).
 */
@Component({
  selector: 'gestion-sponsor-levels-page',
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
  templateUrl: './sponsor-levels-page.html',
  styleUrl: '../page.scss',
  styles: `
    .amount {
      text-align: end;
      white-space: nowrap;
    }
    .lines {
      white-space: pre-line;
    }
  `,
})
export class SponsorLevelsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(SponsorsApi);
  private readonly dialog = inject(MatDialog);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly sizes = LOGO_SIZES;
  protected readonly levels = signal<SponsorLevel[]>([]);
  protected readonly currency = signal('XOF');
  protected readonly editing = signal<SponsorLevel | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('sponsors.write'),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    name_fr: ['', [Validators.required, Validators.maxLength(100)]],
    name_en: ['', Validators.maxLength(100)],
    amount: [''],
    benefits_fr: ['', Validators.maxLength(2000)],
    benefits_en: ['', Validators.maxLength(2000)],
    logo_size: ['medium' as LogoSize],
  });

  async ngOnInit(): Promise<void> {
    const edition = this.edition();
    try {
      const [levels, overview] = await Promise.all([
        this.api.levels(edition),
        this.api.sponsors(edition),
      ]);
      this.levels.set(levels);
      this.currency.set(overview.totals.currency);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected name(level: SponsorLevel): string {
    return levelName(level, this.language.current());
  }

  protected benefits(level: SponsorLevel): string {
    return (this.language.current() === 'en' && level.benefits_en) || level.benefits_fr;
  }

  protected amount(value: string | null): string {
    return money(value, this.currency(), this.language.current());
  }

  protected edit(level: SponsorLevel): void {
    this.editing.set(level);
    this.form.reset({
      name_fr: level.name_fr,
      name_en: level.name_en,
      amount: level.amount ?? '',
      benefits_fr: level.benefits_fr,
      benefits_en: level.benefits_en,
      logo_size: level.logo_size,
    });
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.form.reset();
  }

  protected async submit(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    const body = {
      ...value,
      name_fr: value.name_fr.trim(),
      name_en: value.name_en.trim(),
      amount: value.amount === '' ? null : value.amount,
    };
    const level = this.editing();
    await this.run(
      level ? 'gestion.sponsorLevels.updated' : 'gestion.sponsorLevels.created',
      async () => {
        const levels = level
          ? await this.api.updateLevel(this.edition(), level.id, body)
          : await this.api.createLevel(this.edition(), body);
        this.cancelEdit();
        return levels;
      },
    );
  }

  protected async remove(level: SponsorLevel): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.sponsorLevels.delete',
      {
        name: this.name(level),
      },
    );
    if (!answer) return;
    await this.run('gestion.sponsorLevels.deleted', () =>
      this.api.deleteLevel(this.edition(), level.id),
    );
  }

  private async run(message: string, action: () => Promise<SponsorLevel[]>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.levels.set(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
