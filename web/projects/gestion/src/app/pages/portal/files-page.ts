import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  ErrorSummary,
  LanguageService,
  PageHeader,
  PortalFileKind,
  PublicFile,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { moved, PortalFilesApi } from '../../core/portal-api';
import { PortalStatusBanner } from './portal-status-banner';
import { PortalScreen } from './portal-support';

export const FILE_KINDS: readonly PortalFileKind[] = ['document', 'image'];
const ACCEPT: Record<PortalFileKind, string> = {
  document: '.pdf,.docx,.odt,.zip',
  image: '.png,.jpg,.jpeg,.webp',
};

/**
 * Documents et images publics de l'édition (plan L2 §2.5, E4) : téléversement (type vérifié
 * par le serveur sur le contenu, images réencodées sans métadonnées), titres bilingues,
 * ordre, publication ; affiche de l'édition. Un fichier utilisé ne se supprime pas.
 */
@Component({
  selector: 'gestion-portal-files-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
    PortalStatusBanner,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './files-page.html',
  styleUrl: '../page.scss',
  styles: `
    .thumb {
      max-width: 6rem;
      max-height: 4rem;
      object-fit: contain;
      border: 1px solid var(--gc-border);
    }
    .file-input {
      display: grid;
      gap: 0.25rem;
      margin-bottom: 1rem;
    }
  `,
})
export class FilesPage extends PortalScreen implements OnInit {
  private readonly files = inject(PortalFilesApi);
  private readonly language = inject(LanguageService);
  private readonly banner = viewChild(PortalStatusBanner);
  private readonly fileInput = viewChild<ElementRef<HTMLInputElement>>('fileInput');

  protected readonly kinds = FILE_KINDS;
  protected readonly items = signal<PublicFile[]>([]);
  protected readonly byKind = computed(() => {
    const result: Record<PortalFileKind, PublicFile[]> = { document: [], image: [] };
    for (const item of this.items()) {
      if (item.kind === 'document' || item.kind === 'image') {
        result[item.kind].push(item);
      }
    }
    return result;
  });
  protected readonly poster = signal<number | null>(null);
  protected readonly editing = signal<number | null>(null);
  protected readonly selectedFile = signal<File | null>(null);

  protected readonly uploadForm = inject(NonNullableFormBuilder).group({
    kind: ['document' as PortalFileKind, Validators.required],
    title_fr: ['', Validators.maxLength(255)],
    title_en: ['', Validators.maxLength(255)],
  });
  protected readonly editForm = inject(NonNullableFormBuilder).group({
    title_fr: ['', Validators.maxLength(255)],
    title_en: ['', Validators.maxLength(255)],
    published: [false],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected accept(): string {
    return ACCEPT[this.uploadForm.controls.kind.value];
  }

  protected size(bytes: number): string {
    const units = this.language.current() === 'fr' ? ['o', 'Ko', 'Mo'] : ['B', 'KB', 'MB'];
    let value = bytes;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${new Intl.NumberFormat(this.language.current(), { maximumFractionDigits: 1 }).format(value)} ${units[unit]}`;
  }

  protected chooseFile(event: Event): void {
    this.selectedFile.set((event.target as HTMLInputElement).files?.[0] ?? null);
  }

  protected async upload(): Promise<void> {
    const file = this.selectedFile();
    if (!file) {
      this.errors.set([this.translate.instant('gestion.portal.files.chooseFirst')]);
      return;
    }
    const value = this.uploadForm.getRawValue();
    const done = await this.run(
      () => this.files.upload(this.edition, file, value.kind, value.title_fr, value.title_en),
      'gestion.portal.files.uploaded',
    );
    if (done) {
      this.selectedFile.set(null);
      this.uploadForm.patchValue({ title_fr: '', title_en: '' });
      const input = this.fileInput()?.nativeElement;
      if (input) {
        input.value = '';
      }
      await this.reload();
    }
  }

  protected startEdit(item: PublicFile): void {
    this.editForm.reset({
      title_fr: item.title_fr ?? '',
      title_en: item.title_en ?? '',
      published: item.published ?? false,
    });
    this.editing.set(item.id);
  }

  protected async saveEdit(item: PublicFile): Promise<void> {
    if (
      await this.run(
        () => this.files.update(this.edition, item.id, this.editForm.getRawValue()),
        'gestion.settings.saved',
      )
    ) {
      this.editing.set(null);
      await this.reload();
    }
  }

  /** Ordre : échange des positions des deux voisins (rang affiché = position). */
  protected async move(kind: PortalFileKind, index: number, delta: -1 | 1): Promise<void> {
    const list = moved(this.byKind()[kind], index, delta);
    const changed = list
      .map((item, position) => ({ item, position }))
      .filter(({ item, position }) => item.position !== position);
    if (
      await this.run(async () => {
        for (const { item, position } of changed) {
          await this.files.update(this.edition, item.id, { position });
        }
      }, 'gestion.portal.composer.moved')
    ) {
      await this.reload();
    }
  }

  protected async remove(item: PublicFile): Promise<void> {
    const confirmed = await this.confirm(
      this.translate.instant('gestion.portal.files.deleteTitle'),
      this.translate.instant('gestion.settings.deleteMessage', {
        name: item.title_fr || item.original_name,
      }),
      this.translate.instant('gestion.settings.delete'),
    );
    if (
      confirmed &&
      (await this.run(() => this.files.remove(this.edition, item.id), 'gestion.settings.deleted'))
    ) {
      await this.reload();
    }
  }

  protected async savePoster(value: number | null): Promise<void> {
    if (
      await this.run(
        async () => this.poster.set((await this.files.setPoster(this.edition, value)).file),
        'gestion.settings.saved',
      )
    ) {
      // Relecture : la colonne « Utilisé par » change avec l'affiche.
      await this.reload();
    }
  }

  private async reload(): Promise<void> {
    try {
      const [items, poster] = await Promise.all([
        this.files.files(this.edition),
        this.files.poster(this.edition),
      ]);
      this.items.set(items);
      this.poster.set(poster.file);
      await this.banner()?.refresh();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
