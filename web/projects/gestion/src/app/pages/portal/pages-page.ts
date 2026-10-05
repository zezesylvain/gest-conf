import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { NgTemplateOutlet } from '@angular/common';
import { Router, RouterLink } from '@angular/router';
import { ErrorSummary, fieldErrorMessage, Page, PageHeader } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { PortalStatusBanner } from './portal-status-banner';
import { PortalScreen, SLUG_PATTERN } from './portal-support';

/**
 * Pages du portail (plan L2 §2.2) : pages du site (gabarit codé, adresse figée) et pages
 * personnalisées (`/<langue>/p/<slug>/`). La composition se fait dans le composeur.
 */
@Component({
  selector: 'gestion-portal-pages-page',
  imports: [
    NgTemplateOutlet,
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
    PortalStatusBanner,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './pages-page.html',
  styleUrl: '../page.scss',
})
export class PagesPage extends PortalScreen implements OnInit {
  private readonly router = inject(Router);
  private readonly banner = viewChild(PortalStatusBanner);

  protected readonly pages = signal<Page[]>([]);
  protected readonly sitePages = computed(() => this.pages().filter((page) => page.is_system));
  protected readonly customPages = computed(() => this.pages().filter((page) => !page.is_system));
  protected readonly creating = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    slug: ['', [Validators.required, Validators.maxLength(64), Validators.pattern(SLUG_PATTERN)]],
    title_fr: ['', [Validators.required, Validators.maxLength(255)]],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected error(name: 'slug' | 'title_fr'): string {
    return fieldErrorMessage(this.translate, this.form.controls[name]);
  }

  protected async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.errors.set([]);
    this.busy.set(true);
    try {
      const page = await this.api.createPage(this.edition, this.form.getRawValue());
      await this.router.navigate(['/editions', this.edition, 'portail', 'pages', page.id]);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  protected async remove(page: Page): Promise<void> {
    const confirmed = await this.confirm(
      this.translate.instant('gestion.portal.pages.deleteTitle'),
      this.translate.instant('gestion.portal.pages.deleteMessage', { name: page.title_fr }),
      this.translate.instant('gestion.settings.delete'),
    );
    if (
      confirmed &&
      (await this.run(() => this.api.deletePage(this.edition, page.id), 'gestion.settings.deleted'))
    ) {
      await this.reload();
    }
  }

  private async reload(): Promise<void> {
    try {
      this.pages.set(await this.api.pages(this.edition));
      await this.banner()?.refresh();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
