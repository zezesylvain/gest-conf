import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { Meta } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { GcApiError, LanguageService, PageHeader, Unsubscribed } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { CommunityService } from '../../account/community/community.service';

/**
 * Désabonnement des annonces par le lien de l'e-mail (plan L8, N11) : jeton signé dans
 * l'adresse, sans connexion, page `noindex` sans Material (hors de l'espace compte). Rien ne part sans un clic (un aperçu de lien par une
 * messagerie ne désabonne personne) ; rejouer le lien est sans effet ; un jeton altéré
 * reçoit un message clair. Les e-mails de service restent envoyés.
 */
@Component({
  selector: 'portail-unsubscribe-page',
  imports: [RouterLink, TranslatePipe, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <gc-page-header [heading]="'portail.community.unsubscribe.title' | translate" />
    <div aria-live="polite">
      @switch (state()) {
        @case ('ready') {
          <p>{{ 'portail.community.unsubscribe.lead' | translate }}</p>
          <button class="button primary" type="button" (click)="confirm()" [disabled]="busy()">
            {{ 'portail.community.unsubscribe.confirm' | translate }}
          </button>
        }
        @case ('done') {
          <p role="status">
            {{ 'portail.community.unsubscribe.done' | translate: { edition: editionTitle() } }}
          </p>
          <p>{{ 'portail.community.unsubscribe.service' | translate }}</p>
          <p>
            <a routerLink="/compte/preferences">{{
              'portail.community.unsubscribe.preferences' | translate
            }}</a>
          </p>
        }
        @case ('invalid') {
          <p role="alert">{{ 'portail.community.unsubscribe.invalid' | translate }}</p>
        }
        @case ('error') {
          <p role="alert">{{ 'portail.site.errorLead' | translate }}</p>
        }
      }
    </div>
  `,
  styleUrl: '../../site/site.scss',
})
export class UnsubscribePage implements OnInit, OnDestroy {
  private readonly service = inject(CommunityService);
  private readonly meta = inject(Meta);
  private readonly language = inject(LanguageService);
  private readonly token = inject(ActivatedRoute).snapshot.paramMap.get('token') ?? '';

  protected readonly state = signal<'ready' | 'done' | 'invalid' | 'error'>(
    this.token ? 'ready' : 'invalid',
  );
  protected readonly result = signal<Unsubscribed | null>(null);
  protected readonly busy = signal(false);

  ngOnInit(): void {
    // Lien personnel : jamais indexé.
    this.meta.updateTag({ name: 'robots', content: 'noindex, nofollow' });
  }

  ngOnDestroy(): void {
    this.meta.removeTag('name="robots"');
  }

  protected editionTitle(): string {
    const result = this.result();
    if (!result) return '';
    return (this.language.current() === 'en' && result.edition_title_en) || result.edition_title_fr;
  }

  protected async confirm(): Promise<void> {
    this.busy.set(true);
    try {
      this.result.set(await this.service.unsubscribe(this.token));
      this.state.set('done');
    } catch (error) {
      this.state.set(error instanceof GcApiError && error.status === 400 ? 'invalid' : 'error');
    } finally {
      this.busy.set(false);
    }
  }
}
