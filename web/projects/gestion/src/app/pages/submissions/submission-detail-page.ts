import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import {
  FormGroupDirective,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  ErrorSummary,
  Extension,
  fieldErrorMessage,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
  SubmissionManageDetail,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EditionApi } from '../../core/edition-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { fileUrl, SubmissionsApi } from '../../core/submissions-api';

/**
 * Détail d'une soumission dans la gestion (plan L3 §5, F10) : métadonnées, auteurs avec
 * adresses, versions du PDF (endpoint authentifié), déclarations, historique des statuts,
 * révisions et dérogations (RG-02, F8). Dérogation : échéance saisie à l'heure de l'édition
 * (D13), motif obligatoire, journalisée et notifiée à l'auteur par le serveur.
 */
@Component({
  selector: 'gestion-submission-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './submission-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .abstract {
      white-space: pre-wrap;
    }
    dl {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.25rem 1rem;
      margin: 0;
    }
    dt {
      font-weight: 600;
    }
    dd {
      margin: 0;
    }
    .badge {
      margin-right: 0.25rem;
    }
  `,
})
export class SubmissionDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly submissionId = input.required<string>();

  private readonly api = inject(SubmissionsApi);
  private readonly editions = inject(EditionApi);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly submission = signal<SubmissionManageDetail | null>(null);
  protected readonly timezone = signal<string | undefined>(undefined);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canExtend = computed(
    () =>
      editionCapabilities(this.meStore, this.editionId()).includes('submissions.extend') &&
      (this.submission()?.can_extend ?? false),
  );
  /** Directive du formulaire : `resetForm()` efface aussi l'état « soumis » (erreurs). */
  private readonly extensionDirective = viewChild(FormGroupDirective);
  protected readonly extensionForm = inject(NonNullableFormBuilder).group({
    until_local: ['', Validators.required],
    reason: ['', [Validators.required, Validators.maxLength(2000)]],
  });

  async ngOnInit(): Promise<void> {
    try {
      const [edition, submission] = await Promise.all([
        this.editions.edition(Number(this.editionId())),
        this.api.get(Number(this.editionId()), Number(this.submissionId())),
      ]);
      this.timezone.set(edition.timezone);
      this.submission.set(submission);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected date(value: string | null | undefined): string {
    return value ? formatInZone(value, this.timezone(), this.language.current()) : '—';
  }

  protected download(fileId: number): string {
    return fileUrl(this.editionId(), this.submissionId(), fileId);
  }

  protected error(name: 'until_local' | 'reason'): string {
    return fieldErrorMessage(this.translate, this.extensionForm.controls[name]);
  }

  protected async grant(): Promise<void> {
    this.errors.set([]);
    this.status.set('');
    if (this.extensionForm.invalid) {
      this.extensionForm.markAllAsTouched();
      return;
    }
    this.busy.set(true);
    try {
      const value = this.extensionForm.getRawValue();
      this.submission.set(
        await this.api.grantExtension(Number(this.editionId()), Number(this.submissionId()), {
          until_local: value.until_local,
          reason: value.reason.trim(),
        }),
      );
      this.extensionDirective()?.resetForm();
      this.status.set(this.translate.instant('gestion.submissions.extensions.granted'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.extensionForm));
    } finally {
      this.busy.set(false);
    }
  }

  protected async revoke(extension: Extension): Promise<void> {
    const data: ConfirmDialogData = {
      title: this.translate.instant('gestion.submissions.extensions.revokeTitle'),
      message: this.translate.instant('gestion.submissions.extensions.revokeMessage', {
        date: this.date(extension.until),
      }),
      confirmLabel: this.translate.instant('gestion.submissions.extensions.revoke'),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    if (!(await firstValueFrom(ref.afterClosed()))) {
      return;
    }
    this.errors.set([]);
    this.busy.set(true);
    try {
      this.submission.set(
        await this.api.revokeExtension(
          Number(this.editionId()),
          Number(this.submissionId()),
          extension.id,
        ),
      );
      this.status.set(this.translate.instant('gestion.submissions.extensions.revoked'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}
