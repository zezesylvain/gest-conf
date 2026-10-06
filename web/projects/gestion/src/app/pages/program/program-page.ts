import { computed, Directive, inject, input, OnInit, signal } from '@angular/core';
import { FormGroup } from '@angular/forms';
import { MatDialog } from '@angular/material/dialog';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  LanguageService,
  MeStore,
  ProgramBoard,
} from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { isStaleRevision, ProgramApi } from '../../core/program-api';

/**
 * Base des écrans du programme (plan L5 §5) : brouillon complet en signal, écritures avec la
 * révision lue (`If-Match`, I14) et remplacement du brouillon par la réponse du serveur, qui
 * porte les conflits à jour (RG-12, RG-13). Révision périmée (412) : rechargement et message.
 *
 * `program.write` et `program.publish` n'adaptent que l'interface ; le serveur décide
 * (règle n° 2).
 */
@Directive()
export abstract class ProgramPage implements OnInit {
  readonly editionId = input.required<string>();

  protected readonly api = inject(ProgramApi);
  protected readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);

  protected readonly board = signal<ProgramBoard | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  /** Annonce de la dernière action (région `aria-live`). */
  protected readonly status = signal('');

  private readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly canWrite = computed(() => this.capabilities().includes('program.write'));
  protected readonly canPublish = computed(() => this.capabilities().includes('program.publish'));
  protected readonly lang = computed(() => this.language.current());

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected edition(): number {
    return Number(this.editionId());
  }

  protected async reload(): Promise<void> {
    try {
      this.board.set(await this.api.board(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  /**
   * Écriture du brouillon. Renvoie `true` si le serveur l'a acceptée. Les erreurs de champ
   * vont sur `form` s'il est fourni ; une révision périmée recharge le brouillon.
   */
  protected async write(
    action: (revision: number) => Promise<ProgramBoard>,
    done: string,
    params: Record<string, unknown> = {},
    form?: FormGroup,
  ): Promise<boolean> {
    const board = this.board();
    if (!board) {
      return false;
    }
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.board.set(await action(board.revision));
      this.status.set(this.translate.instant(done, params));
      return true;
    } catch (error) {
      if (isStaleRevision(error)) {
        await this.reload();
        this.errors.set([this.translate.instant('gestion.program.stale')]);
      } else {
        this.errors.set(errorMessages(this.translate, error, form));
      }
      return false;
    } finally {
      this.busy.set(false);
    }
  }

  protected async confirm(key: string, params: Record<string, unknown> = {}): Promise<boolean> {
    const data: ConfirmDialogData = {
      title: this.translate.instant(`${key}.title`),
      message: this.translate.instant(`${key}.message`, params),
      confirmLabel: this.translate.instant(`${key}.confirm`),
    };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return !!(await firstValueFrom(ref.afterClosed()));
  }
}
