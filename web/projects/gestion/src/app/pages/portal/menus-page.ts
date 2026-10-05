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
import { MatRadioModule } from '@angular/material/radio';
import { MatSelectModule } from '@angular/material/select';
import {
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  MenuItem,
  MenuItemRequest,
  MenuLocation,
  Page,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { errorMessages } from '../../core/page-support';
import { moved } from '../../core/portal-api';
import { PortalStatusBanner } from './portal-status-banner';
import { PortalScreen } from './portal-support';

export const MENU_LOCATIONS: readonly MenuLocation[] = ['header', 'footer'];

/**
 * Menus d'en-tête et de pied de page (plan L2 §2.2) : une entrée vise une page **ou** une
 * adresse (`https:`, `mailto:`, `tel:` ou chemin interne). Tant qu'un menu est vide, le
 * portail affiche sa navigation codée.
 */
@Component({
  selector: 'gestion-portal-menus-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatRadioModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
    PortalStatusBanner,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './menus-page.html',
  styleUrl: '../page.scss',
})
export class MenusPage extends PortalScreen implements OnInit {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly banner = viewChild(PortalStatusBanner);

  protected readonly locations = MENU_LOCATIONS;
  protected readonly items = signal<MenuItem[]>([]);
  protected readonly pages = signal<Page[]>([]);
  /** `null` : pas de formulaire ; `0` : création ; sinon : identifiant modifié. */
  protected readonly editing = signal<number | null>(null);
  protected readonly byLocation = computed(() => {
    const result: Record<MenuLocation, MenuItem[]> = { header: [], footer: [] };
    for (const item of this.items()) {
      result[item.location].push(item);
    }
    return result;
  });

  protected readonly form = inject(NonNullableFormBuilder).group({
    location: ['header' as MenuLocation, Validators.required],
    label_fr: ['', [Validators.required, Validators.maxLength(120)]],
    label_en: ['', Validators.maxLength(120)],
    target: ['page' as 'page' | 'url'],
    page: [null as number | null],
    url: ['', Validators.maxLength(500)],
    new_tab: [false],
    published: [true],
  });

  async ngOnInit(): Promise<void> {
    try {
      this.pages.set(await this.api.pages(this.edition));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    await this.reload();
    this.loading.set(false);
  }

  protected error(name: string): string {
    const control = this.form.get(name);
    return control ? fieldErrorMessage(this.translate, control) : '';
  }

  protected target(item: MenuItem): string {
    return item.page_ref ? item.page_ref.title_fr : (item.url ?? '');
  }

  protected startCreate(location: MenuLocation): void {
    this.form.reset({
      location,
      label_fr: '',
      label_en: '',
      target: 'page',
      page: null,
      url: '',
      new_tab: false,
      published: true,
    });
    this.errors.set([]);
    this.editing.set(0);
  }

  protected startEdit(item: MenuItem): void {
    this.form.reset({
      location: item.location,
      label_fr: item.label_fr,
      label_en: item.label_en ?? '',
      target: item.page ? 'page' : 'url',
      page: item.page ?? null,
      url: item.url ?? '',
      new_tab: item.new_tab ?? false,
      published: item.published ?? true,
    });
    this.errors.set([]);
    this.editing.set(item.id);
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    const value = this.form.getRawValue();
    const body: MenuItemRequest = {
      location: value.location,
      label_fr: value.label_fr,
      label_en: value.label_en,
      page: value.target === 'page' ? value.page : null,
      url: value.target === 'url' ? value.url.trim() : '',
      new_tab: value.new_tab,
      published: value.published,
    };
    const id = this.editing();
    this.errors.set([]);
    this.busy.set(true);
    try {
      if (id) {
        await this.api.updateMenuItem(this.edition, id, body);
      } else {
        await this.api.createMenuItem(this.edition, body);
      }
      this.editing.set(null);
      this.status.set(this.translate.instant('gestion.settings.saved'));
      await this.reload();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }

  protected async move(location: MenuLocation, index: number, delta: -1 | 1): Promise<void> {
    const ids = moved(
      this.byLocation()[location].map((item) => item.id),
      index,
      delta,
    );
    if (
      await this.run(
        () => this.api.reorderMenu(this.edition, location, ids),
        'gestion.portal.composer.moved',
      )
    ) {
      await this.reload();
    }
  }

  protected async remove(item: MenuItem): Promise<void> {
    const confirmed = await this.confirm(
      this.translate.instant('gestion.portal.menus.deleteTitle'),
      this.translate.instant('gestion.settings.deleteMessage', { name: item.label_fr }),
      this.translate.instant('gestion.settings.delete'),
    );
    if (
      confirmed &&
      (await this.run(
        () => this.api.deleteMenuItem(this.edition, item.id),
        'gestion.settings.deleted',
      ))
    ) {
      await this.reload();
    }
  }

  private async reload(): Promise<void> {
    try {
      this.items.set(await this.api.menu(this.edition));
      await this.banner()?.refresh();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}
