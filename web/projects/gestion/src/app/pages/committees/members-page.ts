import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  formatInZone,
  LanguageService,
  MemberWithEmail,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { manageableRoles } from '../../core/grantors';
import { editionCapabilities, errorMessages } from '../../core/page-support';

/**
 * Membres de l'édition et leurs rôles (plan L1 §5.5, §10.3). Le serveur filtre la liste
 * selon le rôle (un président du CS ne voit que le comité scientifique) et ne renvoie
 * l'adresse qu'avec `members.manage`. Révocation avec motif, réauthentification récente.
 */
@Component({
  selector: 'gestion-members-page',
  imports: [TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './members-page.html',
  styleUrl: '../page.scss',
})
export class MembersPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);

  protected readonly members = signal<MemberWithEmail[]>([]);
  protected readonly showRevoked = signal(false);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly visible = computed(() =>
    this.members().filter((member) => this.showRevoked() || member.status === 'active'),
  );
  private readonly myRoles = computed(
    () =>
      this.meStore.me()?.editions.find((edition) => String(edition.id) === this.editionId())
        ?.roles ?? [],
  );
  protected readonly canManage = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('members.manage'),
  );

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  /** Bouton de révocation : rôle actif, attribuable par moi, pas mon propre rôle. */
  protected canRevoke(member: MemberWithEmail): boolean {
    return (
      this.canManage() &&
      member.status === 'active' &&
      member.user_id !== this.meStore.me()?.id &&
      (manageableRoles(this.myRoles()) as string[]).includes(member.role)
    );
  }

  protected async revoke(member: MemberWithEmail): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.members.revokeTitle'),
      message: this.translate.instant('gestion.members.revokeMessage', {
        name: member.name,
        role: this.translate.instant(`gestion.roles.${member.role}`),
      }),
      confirmLabel: this.translate.instant('gestion.members.revoke'),
      reasonLabel: this.translate.instant('gestion.members.reason'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '32rem' },
    );
    const result = await firstValueFrom(ref.afterClosed());
    if (!result) {
      return;
    }
    this.errors.set([]);
    try {
      await this.api.revokeMember(Number(this.editionId()), member.id, result.reason);
      this.status.set(this.translate.instant('gestion.members.revoked'));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private async reload(): Promise<void> {
    try {
      this.members.set(await this.api.members(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
