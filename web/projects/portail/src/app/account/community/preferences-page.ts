import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { ErrorSummary, LanguageService, MeStore, PageHeader } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { RegistrationService } from '../registration/registration.service';
import { CommunityService } from './community.service';
import { messagesOf } from './community-support';
import { DietaryCard } from './dietary-card';

/** Édition où le compte a un rôle ou une inscription, avec son abonnement aux annonces. */
interface EditionPreferences {
  id: number;
  label: string;
  subscribed: boolean | null;
}

/**
 * « Régime et annonces » (plan L8, N7, N11) : pour chaque édition où le compte a un rôle ou
 * une inscription, la carte « Régime alimentaire » (RG-23) et l'abonnement aux annonces par
 * e-mail (les e-mails de service et la cloche restent envoyés).
 */
@Component({
  selector: 'portail-preferences-page',
  imports: [TranslatePipe, MatCheckboxModule, ErrorSummary, PageHeader, DietaryCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header
      [heading]="'portail.community.preferences.title' | translate"
      [lead]="'portail.community.preferences.lead' | translate"
    />
    <div aria-live="polite">
      @if (status()) {
        <p class="notice" role="status">{{ status() }}</p>
      }
    </div>
    <gc-error-summary [messages]="errors()" />
    @if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else {
      @for (edition of editions(); track edition.id) {
        <section class="card" [attr.aria-labelledby]="'edition-' + edition.id">
          <h2 [id]="'edition-' + edition.id">{{ edition.label }}</h2>
          @if (edition.subscribed !== null) {
            <mat-checkbox
              [checked]="edition.subscribed"
              [disabled]="busy()"
              (change)="subscribe(edition, $event.checked)"
              >{{ 'portail.community.preferences.announcements' | translate }}</mat-checkbox
            >
            <p class="muted">{{ 'portail.community.preferences.announcementsHint' | translate }}</p>
          }
          <portail-dietary-card [editionId]="edition.id" />
        </section>
      } @empty {
        <p>{{ 'portail.community.preferences.none' | translate }}</p>
      }
    }
  `,
  styleUrl: './community.scss',
})
export class PreferencesPage implements OnInit {
  private readonly service = inject(CommunityService);
  private readonly registrations = inject(RegistrationService);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly editions = signal<EditionPreferences[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  async ngOnInit(): Promise<void> {
    try {
      if (!this.meStore.me()) {
        await this.meStore.load();
      }
      const found = new Map<number, string>();
      for (const edition of this.meStore.me()?.editions ?? []) {
        found.set(edition.id, this.label(edition.code, edition.title_fr, edition.title_en));
      }
      for (const registration of await this.registrations.list().catch(() => [])) {
        const edition = registration.edition;
        if (!found.has(edition.id)) {
          found.set(edition.id, this.label(edition.code, edition.title_fr, edition.title_en));
        }
      }
      const rows = await Promise.all(
        [...found.entries()].map(async ([id, label]) => ({
          id,
          label,
          subscribed: await this.service
            .subscription(id)
            .then((value) => value.subscribed)
            .catch(() => null),
        })),
      );
      this.editions.set(rows);
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected async subscribe(edition: EditionPreferences, subscribed: boolean): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const value = await this.service.setSubscription(edition.id, subscribed);
      this.editions.update((rows) =>
        rows.map((row) => (row.id === edition.id ? { ...row, subscribed: value.subscribed } : row)),
      );
      this.status.set(
        this.translate.instant(
          value.subscribed
            ? 'portail.community.preferences.subscribed'
            : 'portail.community.preferences.unsubscribed',
        ),
      );
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private label(code: string, fr: string, en: string): string {
    return `${code} — ${(this.language.current() === 'en' && en) || fr}`;
  }
}
