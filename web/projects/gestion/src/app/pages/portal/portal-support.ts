import { computed, Directive, inject, input, signal } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import {
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  MeStore,
  SectionType,
} from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { editionCapabilities, errorMessages } from '../../core/page-support';
import { PortalApi } from '../../core/portal-api';

/** Types « données » : contenu lu dans l'édition, la section n'en porte que l'habillage. */
export const DATA_SECTION_TYPES: readonly SectionType[] = [
  'edition_hero',
  'key_dates',
  'tracks',
  'submission_types',
  'documents',
  'committee',
];
export const SECTION_TYPES: readonly SectionType[] = [
  'rich_text',
  'cta_banner',
  'image_text',
  ...DATA_SECTION_TYPES,
];
/** Types qui portent un corps HTML et des boutons d'appel à l'action. */
export const CONTENT_SECTION_TYPES: readonly SectionType[] = [
  'rich_text',
  'cta_banner',
  'image_text',
];

export const SLUG_PATTERN = /^[-a-z0-9]+$/;

/**
 * Base des écrans du portail (plan L2 §2.2) : écriture réservée à `portal.write` dans
 * l'interface ; le serveur décide (règle n° 2).
 */
@Directive()
export abstract class PortalScreen {
  readonly editionId = input.required<string>();

  protected readonly api = inject(PortalApi);
  protected readonly translate = inject(TranslateService);
  private readonly meStore = inject(MeStore);
  private readonly dialog = inject(MatDialog);

  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly busy = signal(false);
  protected readonly loading = signal(true);
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('portal.write'),
  );

  protected get edition(): number {
    return Number(this.editionId());
  }

  /** Exécute une écriture : message de succès, ou erreurs normalisées. */
  protected async run(action: () => Promise<unknown>, successKey?: string): Promise<boolean> {
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      await action();
      if (successKey) {
        this.status.set(this.translate.instant(successKey));
      }
      return true;
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
      return false;
    } finally {
      this.busy.set(false);
    }
  }

  protected async confirm(title: string, message: string, confirmLabel: string): Promise<boolean> {
    const data: ConfirmDialogData = { title, message, confirmLabel };
    const ref = this.dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(
      ConfirmDialog,
      { data, width: '30rem' },
    );
    return Boolean(await firstValueFrom(ref.afterClosed()));
  }
}
