import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  OnDestroy,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { GcApiError, PublicComposition, PublicSite } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { Countdown } from './countdown';
import { PortalData } from './portal-data';
import { PageContext } from './public-portal';
import { SectionsView } from './sections';
import {
  customPagePath,
  localized,
  SITE_PAGES_BY_SLUG,
  sitePagePath,
  SiteLanguage,
} from './site-pages';
import { DatesList, DocumentsList, EditionHero, SubmissionTypesList, TracksList } from './widgets';

/** Dates clés reprises par la page « Appel à communications ». */
const CALL_DATES = ['call_open', 'call_close', 'review_deadline', 'notification', 'camera_ready'];

/**
 * Page du portail public (plan L2 §2.2, §5) : page du site (gabarit codé selon `slug`, puis
 * ses sections) ou page personnalisée (sections seules). Données lues au pré-rendu et
 * transférées au navigateur. `data-gc-rendered` marque une page complète : le contrôle après
 * build refuse une page pré-rendue sans ce marqueur (API en erreur pendant le build).
 */
@Component({
  selector: 'portail-portal-page',
  imports: [
    RouterLink,
    TranslatePipe,
    SectionsView,
    Countdown,
    EditionHero,
    DatesList,
    TracksList,
    SubmissionTypesList,
    DocumentsList,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './portal-page.html',
  styleUrl: './site.scss',
})
export class PortalPage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  /** Langue de l'adresse, page du site (données de la route) ou personnalisée (`:slug`). */
  readonly lang = signal<SiteLanguage>(this.route.snapshot.data['lang'] ?? 'fr');
  readonly custom = signal<boolean>(Boolean(this.route.snapshot.data['custom']));
  readonly slug = signal<string>(
    this.route.snapshot.data['slug'] ?? this.route.snapshot.paramMap.get('slug') ?? '',
  );

  private readonly portal = inject(PortalData);
  private readonly context = inject(PageContext);
  private readonly pendingTasks = inject(PendingTasks);
  private readonly translate = inject(TranslateService);
  private readonly title = inject(Title);
  private readonly meta = inject(Meta);

  protected readonly composition = signal<PublicComposition | null>(null);
  protected readonly site = signal<PublicSite | null>(null);
  protected readonly state = signal<'loading' | 'ready' | 'missing' | 'error'>('loading');
  protected readonly sitePage = computed(() =>
    this.custom() ? null : (SITE_PAGES_BY_SLUG[this.slug()] ?? null),
  );
  protected readonly callDates = computed(() =>
    (this.site()?.edition.key_dates ?? []).filter((item) => CALL_DATES.includes(item.code)),
  );
  /** Titre : celui de la page en base (modifiable dans la gestion), sinon celui du gabarit. */
  protected readonly heading = computed(() => {
    const page = this.composition()?.page ?? this.sitePage();
    return page ? localized(page, 'title', this.lang()) : '';
  });
  protected readonly marker = computed(() =>
    this.state() === 'ready' ? `${this.lang()}:${this.slug()}` : null,
  );

  ngOnInit(): void {
    // Une page personnalisée réutilise ce composant d'un slug à l'autre (même route) :
    // on recharge à chaque changement de paramètre.
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const slug = this.route.snapshot.data['slug'] ?? params.get('slug') ?? '';
      this.slug.set(slug);
      void this.load(slug);
    });
  }

  private async load(slug: string): Promise<void> {
    const lang = this.lang();
    this.state.set('loading');
    this.composition.set(null);
    this.context.set(lang, {
      fr: this.custom() ? customPagePath(slug, 'fr') : sitePagePath(slug, 'fr'),
      en: this.custom() ? customPagePath(slug, 'en') : sitePagePath(slug, 'en'),
    });
    // Le pré-rendu attend la fin de cette tâche (données et rendu complets).
    await this.pendingTasks.run(async () => {
      try {
        const [composition, site] = await Promise.all([
          this.portal.page(slug).catch((error: unknown) => {
            // Page du site sans composition : le gabarit s'affiche seul.
            if (error instanceof GcApiError && error.status === 404 && !this.custom()) {
              return null;
            }
            throw error;
          }),
          this.portal.site(),
        ]);
        this.composition.set(composition);
        this.site.set(site);
        this.state.set(this.custom() && !composition ? 'missing' : 'ready');
        this.describe();
      } catch (error) {
        this.state.set(error instanceof GcApiError && error.status === 404 ? 'missing' : 'error');
        this.title.setTitle(this.translate.instant('portail.notFound.title'));
      }
    });
  }

  ngOnDestroy(): void {
    this.context.clear();
  }

  protected text(item: object, field: string): string {
    return localized(item, field, this.lang());
  }

  protected path(slug: string): string {
    return sitePagePath(slug, this.lang());
  }

  /** Titre de l'onglet et description (référencement complet : L2.6). */
  private describe(): void {
    const lang = this.lang();
    const edition = this.site()?.edition;
    const page = this.composition()?.page;
    const pageTitle = this.heading();
    const editionTitle = edition ? localized(edition, 'title', lang) : '';
    this.title.setTitle([pageTitle, editionTitle].filter(Boolean).join(' · '));
    const description =
      (page && localized(page, 'description', lang)) ||
      (edition && localized(edition, 'theme', lang)) ||
      '';
    if (description) {
      this.meta.updateTag({ name: 'description', content: description });
    }
  }
}
