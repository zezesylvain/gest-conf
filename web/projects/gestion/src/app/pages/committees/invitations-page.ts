import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
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
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  InvitableRole,
  InvitationStatus,
  InvitationWithEmail,
  LanguageService,
  Locale,
  MeStore,
  OcFunction,
  PageHeader,
  SkippedInvitation,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { manageableRoles, OC_FUNCTIONS } from '../../core/grantors';
import { editionCapabilities, errorMessages } from '../../core/page-support';

const PAGE_SIZE = 25;
const MAX_EMAILS = 50;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Adresses séparées par des virgules, points-virgules ou retours à la ligne. */
export function parseEmails(text: string): string[] {
  return [
    ...new Set(
      text
        .split(/[\s,;]+/)
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean),
    ),
  ];
}

/**
 * Invitations des membres de comité (plan L1 §5.7) : envoi groupé (50 adresses au plus,
 * quota horaire côté serveur), relance (3 envois), annulation. Inviter un `ADMIN` ou un
 * `CHAIR` demande une réauthentification récente. Les adresses déjà invitées ou déjà
 * membres sont signalées, sans erreur.
 */
@Component({
  selector: 'gestion-invitations-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './invitations-page.html',
  styleUrl: '../page.scss',
})
export class InvitationsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly language = inject(LanguageService);

  protected readonly ocFunctions = OC_FUNCTIONS;
  protected readonly statuses: InvitationStatus[] = [
    'pending',
    'accepted',
    'declined',
    'cancelled',
    'expired',
  ];
  protected readonly invitations = signal<InvitationWithEmail[]>([]);
  protected readonly count = signal(0);
  protected readonly page = signal(1);
  protected readonly statusFilter = signal<InvitationStatus | ''>('pending');
  protected readonly skipped = signal<SkippedInvitation[]>([]);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly sending = signal(false);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.count() / PAGE_SIZE)));
  protected readonly canManage = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('members.manage'),
  );
  protected readonly roles = computed(() =>
    manageableRoles(
      this.meStore
        .me()
        ?.editions.find((edition) => String(edition.id) === this.editionId())
        ?.roles.map((item) => item.role) ?? [],
    ),
  );
  protected readonly form = inject(NonNullableFormBuilder).group({
    emails: ['', Validators.required],
    role: ['' as InvitableRole | '', Validators.required],
    oc_function: ['' as OcFunction | ''],
    locale: [this.language.current() as Locale],
    message: ['', Validators.maxLength(1000)],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
  }

  protected error(name: 'emails' | 'role' | 'oc_function' | 'message'): string {
    const control = this.form.controls[name];
    if (control.errors?.['emails']) {
      return control.errors['emails'] as string;
    }
    return fieldErrorMessage(this.translate, control);
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected async filter(value: string): Promise<void> {
    this.statusFilter.set(value as InvitationStatus | '');
    this.page.set(1);
    await this.reload();
  }

  protected async goTo(page: number): Promise<void> {
    this.page.set(page);
    await this.reload();
  }

  protected async send(): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    this.skipped.set([]);
    const value = this.form.getRawValue();
    const emails = parseEmails(value.emails);
    const invalid = emails.filter((email) => !EMAIL.test(email));
    if (invalid.length || emails.length > MAX_EMAILS) {
      this.form.controls.emails.setErrors({
        emails: invalid.length
          ? this.translate.instant('gestion.invitations.invalidEmails', {
              emails: invalid.join(', '),
            })
          : this.translate.instant('gestion.invitations.tooMany', { max: MAX_EMAILS }),
      });
    }
    if (value.role === 'OC_MEMBER' && !value.oc_function) {
      this.form.controls.oc_function.setErrors({ required: true });
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.sending.set(true);
    try {
      const batch = await this.api.invite(Number(this.editionId()), {
        emails,
        role: value.role as InvitableRole,
        oc_function: value.role === 'OC_MEMBER' ? (value.oc_function as OcFunction) : '',
        locale: value.locale,
        message: value.message.trim(),
      });
      this.skipped.set(batch.skipped);
      this.status.set(
        this.translate.instant('gestion.invitations.sent', { count: batch.created.length }),
      );
      this.form.reset({
        emails: '',
        role: value.role,
        oc_function: '',
        locale: value.locale,
        message: '',
      });
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.sending.set(false);
    }
  }

  protected async resend(invitation: InvitationWithEmail): Promise<void> {
    await this.act(
      () => this.api.resendInvitation(Number(this.editionId()), invitation.id),
      'gestion.invitations.resent',
    );
  }

  protected async cancelInvitation(invitation: InvitationWithEmail): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.invitations.cancelTitle'),
      message: this.translate.instant('gestion.invitations.cancelMessage', {
        email: invitation.email,
      }),
      confirmLabel: this.translate.instant('gestion.invitations.cancel'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    if (await firstValueFrom(ref.afterClosed())) {
      await this.act(
        () => this.api.cancelInvitation(Number(this.editionId()), invitation.id),
        'gestion.invitations.cancelled',
      );
    }
  }

  private async act(action: () => Promise<unknown>, successKey: string): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
      this.status.set(this.translate.instant(successKey));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private async reload(): Promise<void> {
    try {
      const filter = this.statusFilter();
      const result = await this.api.invitations({
        edition_id: Number(this.editionId()),
        page: this.page(),
        page_size: PAGE_SIZE,
        ...(filter ? { status: filter } : {}),
      });
      this.invitations.set(result.results);
      this.count.set(result.count);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
