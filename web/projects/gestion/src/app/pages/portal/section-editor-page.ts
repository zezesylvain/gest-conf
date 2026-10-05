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
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  PageHeader,
  PatchedSectionWriteRequest,
  Preview,
  PublicFile,
  Section,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { PortalFilesApi } from '../../core/portal-api';
import { CONTENT_SECTION_TYPES, PortalScreen, SLUG_PATTERN } from './portal-support';

/** Les deux langues côte à côte : chaque champ traduisible a sa colonne FR et EN. */
type Translatable = 'title' | 'subtitle' | 'body' | 'cta_label' | 'cta2_label';

/**
 * Édition d'une section (plan L2 §2.2) : champs bilingues côte à côte, champs propres au
 * type, aperçu du HTML tel qu'il sera enregistré (assaini par le serveur). Une colonne
 * anglaise vide se replie sur le français au rendu.
 */
@Component({
  selector: 'gestion-portal-section-editor-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './section-editor-page.html',
  styleUrl: '../page.scss',
  styles: `
    .languages {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
      gap: 0 1.5rem;
    }
    .language h3 {
      margin: 0 0 0.5rem;
      font-size: 1rem;
    }
    textarea {
      font-family: ui-monospace, monospace;
    }
    .preview {
      padding: 0.75rem 1rem;
      border: 1px dashed var(--gc-border);
      border-radius: 0.25rem;
      min-height: 3rem;
    }
  `,
})
export class SectionEditorPage extends PortalScreen implements OnInit {
  /** Paramètre `:sectionId` de la route. */
  readonly sectionId = input.required<string>();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly files = inject(PortalFilesApi);
  protected readonly section = signal<Section | null>(null);
  protected readonly preview = signal<Preview | null>(null);
  protected readonly languages = ['fr', 'en'] as const;

  protected readonly form = inject(NonNullableFormBuilder).group({
    code: ['', [Validators.required, Validators.maxLength(64), Validators.pattern(SLUG_PATTERN)]],
    title_fr: ['', Validators.maxLength(255)],
    title_en: ['', Validators.maxLength(255)],
    subtitle_fr: ['', Validators.maxLength(500)],
    subtitle_en: ['', Validators.maxLength(500)],
    body_fr: ['', Validators.maxLength(20000)],
    body_en: ['', Validators.maxLength(20000)],
    cta_label_fr: ['', Validators.maxLength(120)],
    cta_label_en: ['', Validators.maxLength(120)],
    cta_url: ['', Validators.maxLength(500)],
    cta2_label_fr: ['', Validators.maxLength(120)],
    cta2_label_en: ['', Validators.maxLength(120)],
    cta2_url: ['', Validators.maxLength(500)],
    published: [true],
    // Réglages propres au type (configuration bornée par le serveur).
    countdown: [true],
    limit: [null as number | null, [Validators.min(1), Validators.max(20)]],
    committee: ['scientific'],
    image_position: ['left'],
    image: [null as number | null],
  });
  /** Images publiques de l'édition, pour une section « image et texte ». */
  protected readonly images = signal<PublicFile[]>([]);
  private readonly imageId = signal<number | null>(null);
  protected readonly selectedImage = computed(
    () => this.images().find((image) => image.id === this.imageId()) ?? null,
  );

  protected readonly type = computed(() => this.section()?.section_type ?? null);
  protected readonly hasContent = computed(() => {
    const type = this.type();
    return type !== null && CONTENT_SECTION_TYPES.includes(type);
  });

  async ngOnInit(): Promise<void> {
    try {
      const section = await this.api.section(this.edition, Number(this.sectionId()));
      this.load(section);
      if (section.section_type === 'image_text') {
        this.images.set(await this.files.files(this.edition, 'image'));
      }
      this.form.controls.image.valueChanges.subscribe((value) => this.imageId.set(value));
      this.imageId.set(this.form.controls.image.value);
      if (!this.canWrite()) {
        this.form.disable();
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    this.loading.set(false);
  }

  protected field(name: Translatable, language: 'fr' | 'en'): `${Translatable}_${'fr' | 'en'}` {
    return `${name}_${language}`;
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected async showPreview(): Promise<void> {
    const value = this.form.getRawValue();
    await this.run(async () =>
      this.preview.set(await this.api.preview(this.edition, value.body_fr, value.body_en)),
    );
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      const section = await this.api.updateSection(
        this.edition,
        Number(this.sectionId()),
        this.payload(),
      );
      this.load(section);
      this.status.set(this.translate.instant('gestion.settings.saved'));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }

  private payload(): PatchedSectionWriteRequest {
    const value = this.form.getRawValue();
    const common: PatchedSectionWriteRequest = {
      code: value.code,
      title_fr: value.title_fr,
      title_en: value.title_en,
      subtitle_fr: value.subtitle_fr,
      subtitle_en: value.subtitle_en,
      published: value.published,
      config: this.config(),
    };
    if (!this.hasContent()) {
      return common;
    }
    return {
      ...common,
      ...(this.type() === 'image_text' ? { image: value.image } : {}),
      body_fr: value.body_fr,
      body_en: value.body_en,
      cta_label_fr: value.cta_label_fr,
      cta_label_en: value.cta_label_en,
      cta_url: value.cta_url,
      cta2_label_fr: value.cta2_label_fr,
      cta2_label_en: value.cta2_label_en,
      cta2_url: value.cta2_url,
    };
  }

  /** Configuration du type, seulement les réglages qu'il admet. */
  private config(): Record<string, unknown> {
    const value = this.form.getRawValue();
    switch (this.type()) {
      case 'edition_hero':
        return { countdown: value.countdown };
      case 'key_dates':
      case 'documents':
        return value.limit ? { limit: Number(value.limit) } : {};
      case 'committee':
        return { committee: value.committee };
      case 'image_text':
        return { image_position: value.image_position };
      default:
        return {};
    }
  }

  private load(section: Section): void {
    this.section.set(section);
    const config = (section.config ?? {}) as Record<string, unknown>;
    this.form.reset({
      code: section.code,
      title_fr: section.title_fr ?? '',
      title_en: section.title_en ?? '',
      subtitle_fr: section.subtitle_fr ?? '',
      subtitle_en: section.subtitle_en ?? '',
      body_fr: section.body_fr ?? '',
      body_en: section.body_en ?? '',
      cta_label_fr: section.cta_label_fr ?? '',
      cta_label_en: section.cta_label_en ?? '',
      cta_url: section.cta_url ?? '',
      cta2_label_fr: section.cta2_label_fr ?? '',
      cta2_label_en: section.cta2_label_en ?? '',
      cta2_url: section.cta2_url ?? '',
      published: section.published ?? true,
      countdown: config['countdown'] !== false,
      limit: typeof config['limit'] === 'number' ? config['limit'] : null,
      committee: config['committee'] === 'organizing' ? 'organizing' : 'scientific',
      image_position: config['image_position'] === 'right' ? 'right' : 'left',
      image: section.image ?? null,
    });
  }
}
