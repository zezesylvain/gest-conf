import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  fieldErrorMessage,
  PageHeader,
  Section,
  SectionType,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { PortalStatusBanner } from './portal-status-banner';
import { PortalScreen, SECTION_TYPES, SLUG_PATTERN } from './portal-support';

/**
 * Sections du portail (plan L2 §2.2) : blocs typés réutilisables, chacun indiquant les
 * pages qui le portent. Une section posée ne se supprime pas (le serveur nomme les pages).
 */
@Component({
  selector: 'gestion-portal-sections-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
    PortalStatusBanner,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './sections-page.html',
  styleUrl: '../page.scss',
})
export class SectionsPage extends PortalScreen implements OnInit {
  private readonly router = inject(Router);
  private readonly banner = viewChild(PortalStatusBanner);

  protected readonly types = SECTION_TYPES;
  protected readonly sections = signal<Section[]>([]);
  protected readonly creating = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    section_type: ['rich_text' as SectionType, Validators.required],
    code: ['', [Validators.required, Validators.maxLength(64), Validators.pattern(SLUG_PATTERN)]],
    title_fr: ['', Validators.maxLength(255)],
  });

  async ngOnInit(): Promise<void> {
    await this.reload();
    this.loading.set(false);
  }

  protected error(name: 'code' | 'title_fr'): string {
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
      const section = await this.api.createSection(this.edition, this.form.getRawValue());
      await this.router.navigate(['/editions', this.edition, 'portail', 'sections', section.id]);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  protected async remove(section: Section): Promise<void> {
    const confirmed = await this.confirm(
      this.translate.instant('gestion.portal.sections.deleteTitle'),
      this.translate.instant('gestion.settings.deleteMessage', { name: section.code }),
      this.translate.instant('gestion.settings.delete'),
    );
    if (
      confirmed &&
      (await this.run(
        () => this.api.deleteSection(this.edition, section.id),
        'gestion.settings.deleted',
      ))
    ) {
      await this.reload();
    }
  }

  private async reload(): Promise<void> {
    try {
      this.sections.set(await this.api.sections(this.edition));
      await this.banner()?.refresh();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
