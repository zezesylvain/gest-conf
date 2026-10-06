import {
  computed,
  Directive,
  DOCUMENT,
  inject,
  OnDestroy,
  OnInit,
  PendingTasks,
  signal,
} from '@angular/core';
import { Meta, Title } from '@angular/platform-browser';
import { ActivatedRoute } from '@angular/router';
import { GcApiError, PublicSite } from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';

import { PortalData } from '../portal-data';
import { PageContext } from '../public-portal';
import { applySeo, clearSeo } from '../seo';
import { localized, SiteLanguage } from '../site-pages';
import { dayLabel, programPath, timeIn } from './program-support';

/**
 * Base des pages « jour » et « session » du programme public (plan L5, I7) : langue de
 * l'adresse, sélecteur de langue, lecture pendant le pré-rendu (page complète marquée
 * `data-gc-rendered`, contrôlée après build), titre et référencement comme les pages du site.
 */
@Directive()
export abstract class ProgramRoutePage implements OnInit, OnDestroy {
  protected readonly route = inject(ActivatedRoute);
  readonly lang = signal<SiteLanguage>(this.route.snapshot.data['lang'] ?? 'fr');

  private readonly portal = inject(PortalData);
  private readonly context = inject(PageContext);
  private readonly pendingTasks = inject(PendingTasks);
  protected readonly translate = inject(TranslateService);
  private readonly documentTitle = inject(Title);
  private readonly meta = inject(Meta);
  private readonly document = inject(DOCUMENT);

  protected readonly state = signal<'loading' | 'ready' | 'missing' | 'error'>('loading');
  protected readonly site = signal<PublicSite | null>(null);
  protected readonly marker = computed(() =>
    this.state() === 'ready' ? `${this.lang()}:${this.markerKey()}` : null,
  );

  /** Adresses de la page dans les deux langues (sélecteur de langue, `hreflang`). */
  protected abstract paths(): Record<SiteLanguage, string>;
  /** Lecture des données propres à la page. */
  protected abstract fetch(): Promise<void>;
  protected abstract heading(): string;
  protected abstract markerKey(): string;

  async ngOnInit(): Promise<void> {
    this.context.set(this.lang(), this.paths());
    await this.pendingTasks.run(async () => {
      try {
        const [, site] = await Promise.all([this.fetch(), this.portal.site()]);
        this.site.set(site);
        this.state.set('ready');
        this.describe();
      } catch (error) {
        this.state.set(error instanceof GcApiError && error.status === 404 ? 'missing' : 'error');
        this.documentTitle.setTitle(this.translate.instant('portail.notFound.title'));
        clearSeo(this.document);
      }
    });
  }

  ngOnDestroy(): void {
    this.context.clear();
    clearSeo(this.document);
  }

  protected programLink(): string {
    return programPath(this.lang());
  }

  protected day(date: string): string {
    return dayLabel(date, this.lang());
  }

  protected time(iso: string, timeZone: string): string {
    return timeIn(iso, timeZone, this.lang());
  }

  protected text(item: object, field: string): string {
    return localized(item, field, this.lang());
  }

  private describe(): void {
    const site = this.site();
    if (!site) {
      return;
    }
    const lang = this.lang();
    const edition = site.edition;
    const title = [this.heading(), localized(edition, 'title', lang)].filter(Boolean).join(' · ');
    this.documentTitle.setTitle(title);
    const description = localized(edition, 'theme', lang);
    if (description) {
      this.meta.updateTag({ name: 'description', content: description });
    } else {
      this.meta.removeTag('name="description"');
    }
    applySeo(this.document, {
      siteUrl: site.site_url,
      language: lang,
      paths: this.paths(),
      title,
      description,
      edition,
      poster: site.poster,
      event: false,
    });
  }
}
