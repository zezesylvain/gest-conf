import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  input,
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
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  Page,
  PageHeader,
  PatchedPageRequest,
  Section,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { moved } from '../../core/portal-api';
import { PortalStatusBanner } from './portal-status-banner';
import { PortalScreen, SLUG_PATTERN } from './portal-support';

/**
 * Composeur d'une page (plan L2 §2.2) : informations de la page, puis sections posées,
 * ordonnées par « monter » / « descendre » (pas de glisser-déposer). L'ordre part en liste
 * complète ; chaque écriture renvoie la composition relue depuis la base.
 */
@Component({
  selector: 'gestion-portal-page-composer-page',
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
    PortalStatusBanner,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './page-composer-page.html',
  styleUrl: '../page.scss',
  styles: `
    .composition {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.5rem;
    }
    .composition li {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--gc-border);
      border-radius: 0.25rem;
    }
    .composition .position {
      font-weight: 700;
      margin-right: 0.5rem;
    }
    .template {
      font-style: italic;
      background: var(--gc-surface-muted);
    }
  `,
})
export class PageComposerPage extends PortalScreen implements OnInit {
  /** Paramètre `:pageId` de la route. */
  readonly pageId = input.required<string>();

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly banner = viewChild(PortalStatusBanner);
  protected readonly page = signal<Page | null>(null);
  protected readonly sections = signal<Section[]>([]);
  protected readonly selected = signal<number | null>(null);

  protected readonly form = inject(NonNullableFormBuilder).group({
    slug: ['', [Validators.required, Validators.maxLength(64), Validators.pattern(SLUG_PATTERN)]],
    title_fr: ['', [Validators.required, Validators.maxLength(255)]],
    title_en: ['', Validators.maxLength(255)],
    description_fr: ['', Validators.maxLength(300)],
    description_en: ['', Validators.maxLength(300)],
    published: [true],
  });

  /** Sections que l'on peut encore poser sur cette page. */
  protected readonly available = computed(() => {
    const placed = new Set(this.page()?.sections.map((item) => item.section.id) ?? []);
    return this.sections().filter((section) => !placed.has(section.id));
  });

  async ngOnInit(): Promise<void> {
    try {
      const [page, sections] = await Promise.all([
        this.api.page(this.edition, Number(this.pageId())),
        this.api.sections(this.edition),
      ]);
      this.sections.set(sections);
      this.load(page);
      if (!this.canWrite()) {
        this.form.disable();
      }
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    this.loading.set(false);
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected async saveInfo(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const value = this.form.getRawValue();
    const body: PatchedPageRequest = {
      title_fr: value.title_fr,
      title_en: value.title_en,
      description_fr: value.description_fr,
      description_en: value.description_en,
      ...(this.page()?.is_system ? {} : { slug: value.slug, published: value.published }),
    };
    this.errors.set([]);
    this.status.set('');
    this.busy.set(true);
    try {
      this.load(await this.api.updatePage(this.edition, this.id(), body));
      this.status.set(this.translate.instant('gestion.settings.saved'));
      await this.banner()?.refresh();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  protected async attach(): Promise<void> {
    const section = this.selected();
    if (section === null) {
      return;
    }
    await this.compose(
      () => this.api.attach(this.edition, this.id(), section),
      'gestion.portal.composer.attached',
    );
    this.selected.set(null);
  }

  protected async detach(sectionId: number): Promise<void> {
    await this.compose(
      () => this.api.detach(this.edition, this.id(), sectionId),
      'gestion.portal.composer.detached',
    );
  }

  protected async move(index: number, delta: -1 | 1): Promise<void> {
    const ids = moved(this.page()?.sections.map((item) => item.section.id) ?? [], index, delta);
    await this.compose(
      () => this.api.reorder(this.edition, this.id(), ids),
      'gestion.portal.composer.moved',
    );
  }

  private id(): number {
    return Number(this.pageId());
  }

  /** Écriture de composition : la page renvoyée (relue en base) remplace l'affichage. */
  private async compose(action: () => Promise<Page>, successKey: string): Promise<void> {
    let page: Page | null = null;
    if (await this.run(async () => (page = await action()), successKey)) {
      this.load(page!);
      await this.banner()?.refresh();
    }
  }

  private load(page: Page): void {
    this.page.set(page);
    this.form.reset({
      slug: page.slug,
      title_fr: page.title_fr,
      title_en: page.title_en ?? '',
      description_fr: page.description_fr ?? '',
      description_en: page.description_en ?? '',
      published: page.published ?? true,
    });
    if (page.is_system) {
      this.form.controls.slug.disable();
      this.form.controls.published.disable();
    }
  }
}
