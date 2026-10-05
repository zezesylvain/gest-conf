import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import {
  AcceptedRole,
  apiErrorMessage,
  ErrorSummary,
  formatInZone,
  GcApiError,
  InvitationLookup,
  LanguageService,
  MeStore,
  PageHeader,
  SessionStore,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { AccountService } from '../account.service';
import { takeFragmentKey } from '../fragment-key';
import { PendingInvitation } from '../pending-invitation';

type InvitationState =
  'loading' | 'missing' | 'details' | 'link' | 'accepted' | 'declined' | 'linkSent';

/** Codes pour lesquels la liaison de l'adresse invitée est proposée (RG-20). */
const NEEDS_LINK = new Set(['invitation_email_mismatch', 'invitation_email_unverified']);

/**
 * Invitation à rejoindre une édition (plan L1 §5.7, §10.2 ; RG-20).
 *
 * - `#<jeton>` : consultation (adresse masquée), refus possible sans compte ; acceptation
 *   par un compte qui **contrôle** l'adresse invitée (vérifiée). Sinon : lien de
 *   confirmation envoyé à l'adresse invitée (réauthentification récente).
 * - `#lier=<lien>` : ouvert depuis le même compte, dans l'heure ; ajoute l'adresse comme
 *   vérifiée puis accepte. Une nouvelle réauthentification est demandée si la précédente
 *   date de plus de 5 min.
 *
 * Le jeton seul ne donne jamais de rôle. Il est effacé de la barre d'adresse et gardé en
 * mémoire le temps d'une connexion.
 */
@Component({
  selector: 'portail-invitation-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './invitation-page.html',
  styleUrl: './account-form.scss',
})
export class InvitationPage implements OnInit {
  private readonly account = inject(AccountService);
  private readonly pending = inject(PendingInvitation);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  protected readonly session = inject(SessionStore);
  protected readonly language = inject(LanguageService);

  protected readonly state = signal<InvitationState>('loading');
  protected readonly invitation = signal<InvitationLookup | null>(null);
  protected readonly accepted = signal<AcceptedRole | null>(null);
  protected readonly offerLink = signal(false);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly loginQuery = { next: '/compte/invitation' };
  protected readonly title = computed(() => {
    const invitation = this.invitation();
    if (!invitation) {
      return '';
    }
    return this.language.current() === 'en' && invitation.edition_title_en
      ? invitation.edition_title_en
      : invitation.edition_title_fr;
  });

  async ngOnInit(): Promise<void> {
    this.pending.take(takeFragmentKey(this.document));
    if (this.pending.link()) {
      this.state.set('link');
      return;
    }
    const token = this.pending.token();
    if (!token) {
      this.state.set('missing');
      return;
    }
    try {
      this.invitation.set(await this.account.lookupInvitation(token));
      this.state.set('details');
    } catch (error) {
      this.fail(error);
      this.state.set('missing');
    }
  }

  protected expires(invitation: InvitationLookup): string {
    return formatInZone(invitation.expires_at, undefined, this.language.current());
  }

  protected async accept(): Promise<void> {
    const token = this.pending.token();
    if (token) {
      await this.run(async () => this.done(await this.account.acceptInvitation(token)));
    }
  }

  protected async acceptWithLink(): Promise<void> {
    const link = this.pending.link();
    if (link) {
      await this.run(async () => this.done(await this.account.acceptInvitationLink(link)));
    }
  }

  protected async decline(): Promise<void> {
    const token = this.pending.token();
    if (token) {
      await this.run(async () => {
        await this.account.declineInvitation(token);
        this.pending.clear();
        this.state.set('declined');
      });
    }
  }

  protected async requestLink(): Promise<void> {
    const token = this.pending.token();
    if (token) {
      await this.run(async () => {
        await this.account.requestInvitationLink(token);
        this.state.set('linkSent');
      });
    }
  }

  protected managementUrl(role: AcceptedRole): string {
    return `/gestion/editions/${role.edition_id}`;
  }

  private async done(role: AcceptedRole): Promise<void> {
    this.pending.clear();
    this.accepted.set(role);
    this.state.set('accepted');
    await this.meStore.load().catch(() => undefined);
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.errors.set([]);
    this.busy.set(true);
    try {
      await action();
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy.set(false);
    }
  }

  private fail(error: unknown): void {
    if (error instanceof GcApiError && NEEDS_LINK.has(error.code)) {
      this.offerLink.set(true);
    }
    if (error instanceof GcApiError && error.status === 404) {
      this.errors.set([this.translate.instant('portail.account.invitation.notFound')]);
      return;
    }
    this.errors.set([apiErrorMessage(this.translate, error)]);
  }
}
