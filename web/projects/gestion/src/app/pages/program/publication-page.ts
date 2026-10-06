import { ChangeDetectionStrategy, Component, computed, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { ErrorSummary, formatInZone, PageHeader, Publication } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { ProgramPage } from './program-page';

/** Résumé des différences d'une publication (`ProgramPublication.summary`, L5.4). */
interface PublicationSummary {
  sessions?: { added?: number; changed?: number; removed?: number };
  people?: { added?: number; changed?: number; removed?: number };
}

/**
 * Publication du programme (plan L5, I6, I13, I16 ; RG-17) : conflits restants, modifications
 * non publiées, publication confirmée (Chair, réauthentification récente demandée par
 * l'intercepteur), historique des versions. Le programme public n'apparaît qu'après la
 * republication du portail (I7) : l'écran le rappelle.
 */
@Component({
  selector: 'gestion-publication-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './publication-page.html',
  styleUrl: '../page.scss',
})
export class PublicationPage extends ProgramPage {
  protected readonly history = signal<Publication[] | null>(null);
  protected readonly publishable = computed(() => {
    const board = this.board();
    return !!board && !board.conflicts.length && board.unpublished_changes;
  });

  override async ngOnInit(): Promise<void> {
    await Promise.all([super.ngOnInit(), this.loadHistory()]);
  }

  protected async loadHistory(): Promise<void> {
    try {
      this.history.set(await this.api.publications(this.edition()));
    } catch (error) {
      this.errors.set([...this.errors(), ...errorMessages(this.translate, error)]);
    }
  }

  protected at(publication: Publication): string {
    return formatInZone(publication.published_at, this.board()?.timezone, this.lang());
  }

  protected summary(publication: Publication): string {
    const summary = (publication.summary ?? {}) as PublicationSummary;
    return this.translate.instant('gestion.program.publication.diff', {
      sessionsAdded: summary.sessions?.added ?? 0,
      sessionsChanged: summary.sessions?.changed ?? 0,
      sessionsRemoved: summary.sessions?.removed ?? 0,
      peopleNotified:
        (summary.people?.added ?? 0) +
        (summary.people?.changed ?? 0) +
        (summary.people?.removed ?? 0),
    });
  }

  protected async publish(): Promise<void> {
    const board = this.board();
    if (!board) {
      return;
    }
    if (
      !(await this.confirm('gestion.program.publication.confirm', {
        version: board.published_version + 1,
      }))
    ) {
      return;
    }
    const done = await this.write(
      (revision) => this.api.publish(this.edition(), revision),
      'gestion.program.publication.done',
      { version: board.published_version + 1 },
    );
    if (done) {
      await this.loadHistory();
    }
  }
}
