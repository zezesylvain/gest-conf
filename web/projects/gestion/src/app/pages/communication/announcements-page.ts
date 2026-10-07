import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import {
  Announcement,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  Segment,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunicationApi } from '../../core/communication-api';
import { errorMessages } from '../../core/page-support';
import { CHANNELS } from './communication-support';

/**
 * Annonces (plan L8, N10, N11 ; `communications.send`) : canaux, segment, état de l'envoi ;
 * création d'un brouillon par son titre, complété ensuite dans sa fiche.
 */
@Component({
  selector: 'gestion-announcements-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './announcements-page.html',
  styleUrl: '../page.scss',
})
export class AnnouncementsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(CommunicationApi);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly channels = CHANNELS;
  protected readonly announcements = signal<Announcement[]>([]);
  protected readonly segments = signal<Segment[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected readonly form = inject(NonNullableFormBuilder).group({
    title_fr: ['', [Validators.required, Validators.maxLength(150)]],
  });

  async ngOnInit(): Promise<void> {
    const edition = Number(this.editionId());
    try {
      const [announcements, segments] = await Promise.all([
        this.api.announcements(edition),
        this.api.segments(edition),
      ]);
      this.announcements.set(announcements);
      this.segments.set(segments);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected title(item: Announcement): string {
    return (this.language.current() === 'en' && item.title_en) || item.title_fr;
  }

  protected segmentLabel(code: string): string {
    if (!code) return '—';
    return this.segments().find((segment) => segment.code === code)?.label ?? code;
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      const created = await this.api.createAnnouncement(Number(this.editionId()), {
        title_fr: this.form.getRawValue().title_fr.trim(),
      });
      await this.router.navigate([
        '/editions',
        this.editionId(),
        'communication',
        'annonces',
        created.id,
      ]);
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
