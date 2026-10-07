import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { GcApiError, PublicSpeakers, PublicSpeakerTalk } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { dayLabel, inLanguage, sessionPath, timeIn } from '../program/program-support';
import { SiteLanguage } from '../site-pages';
import { CommunityData } from './community-data';

/**
 * Page publique « Intervenants » (plan L8, N6) : intervenants invités du **programme
 * publié**, avec leur biographie et leur photo quand ils y ont consenti (L2), et leurs
 * passages, à l'heure de la conférence, reliés à la page de la session. Avant la première
 * publication du programme, la page le dit.
 */
@Component({
  selector: 'portail-speakers-overview',
  imports: [RouterLink, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @switch (state()) {
      @case ('loading') {
        <p role="status" class="muted">{{ 'portail.site.loading' | translate }}</p>
      }
      @case ('unpublished') {
        <p class="soon">{{ 'portail.community.speakersUnpublished' | translate }}</p>
      }
      @case ('error') {
        <p>{{ 'portail.site.errorLead' | translate }}</p>
      }
      @case ('ready') {
        @let current = data()!;
        @if (current.speakers.length) {
          <p class="muted">
            {{ 'portail.program.timezone' | translate: { zone: current.timezone } }}
          </p>
          <ul class="cards large">
            @for (speaker of current.speakers; track $index) {
              <li class="card speaker" [class.no-photo]="!speaker.photo_url">
                @if (speaker.photo_url) {
                  <img [src]="speaker.photo_url" alt="" loading="lazy" />
                }
                <div>
                  <h2>{{ speaker.name }}</h2>
                  @if (speaker.institution) {
                    <p class="muted">{{ speaker.institution }}</p>
                  }
                  @if (speaker.bio) {
                    <p>{{ speaker.bio }}</p>
                  }
                  <ul class="talks">
                    @for (talk of speaker.talks; track $index) {
                      <li>
                        <a [routerLink]="session(talk)">{{ title(talk) }}</a>
                        — {{ when(talk, current.timezone) }}
                        @if (talk.room) {
                          · {{ talk.room }}
                        }
                      </li>
                    }
                  </ul>
                </div>
              </li>
            }
          </ul>
        } @else {
          <p class="soon">{{ 'portail.community.noSpeaker' | translate }}</p>
        }
      }
    }
  `,
  styleUrls: ['../site.scss', './community.scss'],
})
export class SpeakersOverview implements OnInit {
  readonly language = input.required<SiteLanguage>();

  private readonly community = inject(CommunityData);
  private readonly pendingTasks = inject(PendingTasks);

  protected readonly data = signal<PublicSpeakers | null>(null);
  protected readonly state = signal<'loading' | 'ready' | 'unpublished' | 'error'>('loading');

  async ngOnInit(): Promise<void> {
    await this.pendingTasks.run(async () => {
      try {
        this.data.set(await this.community.speakers());
        this.state.set('ready');
      } catch (error) {
        this.state.set(
          error instanceof GcApiError && error.status === 404 ? 'unpublished' : 'error',
        );
      }
    });
  }

  protected title(talk: PublicSpeakerTalk): string {
    const own = inLanguage(talk.title_fr, talk.title_en, this.language());
    return own || inLanguage(talk.session_title_fr, talk.session_title_en, this.language());
  }

  protected session(talk: PublicSpeakerTalk): string {
    return sessionPath(talk.session_id, this.language());
  }

  /** « mardi 1 juin 2027, 11:00 » à l'heure de la conférence. */
  protected when(talk: PublicSpeakerTalk, zone: string): string {
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: zone }).format(
      new Date(talk.starts_at),
    );
    return `${dayLabel(day, this.language())}, ${timeIn(talk.starts_at, zone, this.language())}`;
  }
}
