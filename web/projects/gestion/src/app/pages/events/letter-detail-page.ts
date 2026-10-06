import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  ManageLetterDetail,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { confirmAction } from './events-support';

/**
 * Fiche d'une demande de lettre d'invitation (plan L7, K12) : données du passeport (numéro
 * en clair ici seulement), séjour, ambassade ; instruction : émettre (lettre PDF signée par
 * le signataire désigné, vérifiable publiquement), refuser (motif communiqué), révoquer une
 * lettre émise (motif). Émission et révocation avec réauthentification.
 */
@Component({
  selector: 'gestion-letter-detail-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './letter-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    dl {
      display: grid;
      grid-template-columns: minmax(10rem, max-content) 1fr;
      gap: 0.35rem 1rem;
      margin: 0;
    }
    dt {
      font-weight: 600;
    }
    dd {
      margin: 0;
    }
  `,
})
export class LetterDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly letterId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly letter = signal<ManageLetterDetail | null>(null);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');

  async ngOnInit(): Promise<void> {
    try {
      this.letter.set(await this.api.letter(this.edition(), Number(this.letterId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected pdfUrl(letter: ManageLetterDetail): string {
    return eventsUrls.letterPdf(this.editionId(), letter.id);
  }

  protected async issue(letter: ManageLetterDetail): Promise<void> {
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.letters.issue', {
      name: letter.passport_name,
    });
    if (!answer) return;
    await this.act('gestion.letters.issue.done', () =>
      this.api.issueLetter(this.edition(), letter.id),
    );
  }

  protected async refuse(letter: ManageLetterDetail): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.letters.refuse',
      { name: letter.passport_name },
      true,
    );
    if (!answer) return;
    await this.act('gestion.letters.refuse.done', () =>
      this.api.refuseLetter(this.edition(), letter.id, answer.reason.trim()),
    );
  }

  protected async revoke(letter: ManageLetterDetail): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.letters.revoke',
      { name: letter.passport_name },
      true,
    );
    if (!answer) return;
    await this.act('gestion.letters.revoke.done', () =>
      this.api.revokeLetter(this.edition(), letter.id, answer.reason.trim()),
    );
  }

  private async act(done: string, action: () => Promise<ManageLetterDetail>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.letter.set(await action());
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
