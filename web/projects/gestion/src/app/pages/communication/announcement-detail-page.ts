import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  AnnouncementDetail,
  AnnouncementPreview,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  Segment,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunicationApi } from '../../core/communication-api';
import { errorMessages } from '../../core/page-support';
import { confirmAction } from '../events/events-support';

/**
 * Fiche d'une annonce (plan L8, N10, N11, RG-22) : textes FR et EN (HTML assaini par le
 * serveur), canaux, segment et bandeau (fenêtre **en heure locale de l'édition**, D13) ;
 * aperçu de l'e-mail, essai à soi-même, publication sous réauthentification, retrait,
 * annulation de l'envoi, suppression d'un brouillon. Une fois publiée, la cloche, l'e-mail
 * et le segment ne changent plus : l'envoi est parti.
 */
@Component({
  selector: 'gestion-announcement-detail-page',
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
  templateUrl: './announcement-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .checks {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 1rem;
    }
    pre {
      white-space: pre-wrap;
      font: inherit;
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
      max-height: 24rem;
      overflow: auto;
    }
  `,
})
export class AnnouncementDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly announcementId = input.required<string>();

  private readonly api = inject(CommunicationApi);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly announcement = signal<AnnouncementDetail | null>(null);
  protected readonly segments = signal<Segment[]>([]);
  protected readonly preview = signal<AnnouncementPreview | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly form = this.fb.group({
    title_fr: ['', [Validators.required, Validators.maxLength(150)]],
    title_en: ['', Validators.maxLength(150)],
    body_fr: [''],
    body_en: [''],
    on_news: [false],
    on_banner: [false],
    on_bell: [false],
    by_email: [false],
    segment: [''],
    banner_message_fr: ['', Validators.maxLength(280)],
    banner_message_en: ['', Validators.maxLength(280)],
    banner_starts_local: [''],
    banner_ends_local: [''],
  });

  async ngOnInit(): Promise<void> {
    try {
      const [announcement, segments] = await Promise.all([
        this.api.announcement(this.edition(), this.id()),
        this.api.segments(this.edition()),
      ]);
      this.segments.set(segments);
      this.show(announcement);
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
    return Number(this.announcementId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected segmentOption(segment: Segment): string {
    return this.translate.instant('gestion.announcements.segmentOption', {
      label: segment.label,
      count: segment.recipients,
    });
  }

  /** Destinataires du segment choisi, pour la confirmation de publication. */
  private recipients(): number {
    const code = this.form.controls.segment.value;
    return this.segments().find((segment) => segment.code === code)?.recipients ?? 0;
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { on_bell, by_email, segment, ...value } = this.form.getRawValue();
    // Après publication, la cloche, l'e-mail et le segment ne sont plus envoyés : figés.
    const sending = this.announcement()?.status === 'draft' ? { on_bell, by_email, segment } : {};
    await this.run('gestion.announcements.detail.saved', () =>
      this.api.updateAnnouncement(this.edition(), this.id(), {
        ...value,
        ...sending,
        title_fr: value.title_fr.trim(),
        title_en: value.title_en.trim(),
        banner_starts_local: value.banner_starts_local || null,
        banner_ends_local: value.banner_ends_local || null,
      }),
    );
  }

  protected async showPreview(locale: 'fr' | 'en'): Promise<void> {
    this.errors.set([]);
    try {
      this.preview.set(await this.api.preview(this.edition(), this.id(), locale));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  protected async sendTest(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await this.api.sendTest(this.edition(), this.id());
      this.status.set(this.translate.instant('gestion.announcements.detail.testSent'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async publish(): Promise<void> {
    const announcement = this.announcement();
    if (!announcement) return;
    const value = this.form.getRawValue();
    const prefix =
      value.on_bell || value.by_email
        ? 'gestion.announcements.detail.publishSend'
        : 'gestion.announcements.detail.publish';
    const answer = await confirmAction(this.dialog, this.translate, prefix, {
      title: announcement.title_fr,
      count: this.recipients(),
    });
    if (!answer) return;
    await this.run('gestion.announcements.detail.published', () =>
      this.api.publishAnnouncement(this.edition(), this.id()),
    );
  }

  protected async withdraw(): Promise<void> {
    const announcement = this.announcement();
    if (!announcement) return;
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.announcements.detail.withdraw',
      { title: announcement.title_fr },
    );
    if (!answer) return;
    await this.run('gestion.announcements.detail.withdrawn', () =>
      this.api.withdrawAnnouncement(this.edition(), this.id()),
    );
  }

  protected async cancelSending(): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.announcements.detail.cancel',
      {},
    );
    if (!answer) return;
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      const { cancelled } = await this.api.cancelSending(this.edition(), this.id());
      this.show(await this.api.announcement(this.edition(), this.id()));
      this.status.set(
        this.translate.instant('gestion.announcements.detail.cancelled', { count: cancelled }),
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async remove(): Promise<void> {
    const announcement = this.announcement();
    if (!announcement) return;
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.announcements.delete',
      { title: announcement.title_fr },
    );
    if (!answer) return;
    this.busy.set(true);
    this.errors.set([]);
    try {
      await this.api.deleteAnnouncement(this.edition(), announcement.id);
      await this.router.navigate(['/editions', this.editionId(), 'communication', 'annonces']);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async run(message: string, action: () => Promise<AnnouncementDetail>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.show(await action());
      this.preview.set(null);
      this.status.set(this.translate.instant(message));
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private show(announcement: AnnouncementDetail): void {
    this.announcement.set(announcement);
    this.form.reset({
      title_fr: announcement.title_fr,
      title_en: announcement.title_en,
      body_fr: announcement.body_fr,
      body_en: announcement.body_en,
      on_news: announcement.on_news,
      on_banner: announcement.on_banner,
      on_bell: announcement.on_bell,
      by_email: announcement.by_email,
      segment: announcement.segment,
      banner_message_fr: announcement.banner_message_fr,
      banner_message_en: announcement.banner_message_en,
      banner_starts_local: announcement.banner_starts_local ?? '',
      banner_ends_local: announcement.banner_ends_local ?? '',
    });
    // Une fois publiée, l'envoi est parti : cloche, e-mail et segment figés (le serveur
    // refuse de toute façon de les changer). Une annonce retirée ne se modifie plus.
    this.form.enable();
    if (announcement.status !== 'draft') {
      for (const name of ['on_bell', 'by_email', 'segment'] as const) {
        this.form.controls[name].disable();
      }
    }
    if (announcement.status === 'withdrawn') {
      this.form.disable();
    }
  }
}
