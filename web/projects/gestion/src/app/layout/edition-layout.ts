import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  OnDestroy,
  signal,
  untracked,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { ActiveContext, LanguageService, MeStore, Role } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';
import { filter, map } from 'rxjs';

import { editionTitle, managedEditions } from '../core/managed-editions';
import { activeGroup, NavGroup, NavGroupKey } from '../core/navigation';
import { NavigationStore } from '../core/navigation-store';
import { Connectivity } from '../core/reception';

/**
 * Mise en page d'une édition : sélecteurs d'édition et de rôle actif, rail en catégories
 * rétractables filtré par les capacités de `/me` dans cette édition (plan L1 §10.3, plan L2
 * §2.3). L'édition active est dans l'URL et mémorisée comme dernière utilisée.
 */
@Component({
  selector: 'gestion-edition-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './edition-layout.html',
  styleUrl: './edition-layout.scss',
})
export class EditionLayout implements OnDestroy {
  /** Paramètre `:editionId` de la route (liaison des entrées du routeur). */
  readonly editionId = input.required<string>();

  private readonly meStore = inject(MeStore);
  private readonly context = inject(ActiveContext);
  private readonly router = inject(Router);
  protected readonly language = inject(LanguageService);
  protected readonly navigation = inject(NavigationStore);

  protected readonly editions = computed(() => managedEditions(this.meStore));
  protected readonly edition = this.navigation.edition;
  protected readonly managementRoles = this.navigation.managementRoles;
  protected readonly activeRole = this.navigation.activeRole;
  protected readonly groups = this.navigation.groups;
  /**
   * Démarrée sans réseau (plan L7, K5), la gestion ignore `/me` : seul l'écran d'accueil,
   * dont la garde laisse passer, s'affiche ; le serveur revérifiera chaque pointage.
   */
  private readonly connectivity = inject(Connectivity);
  protected readonly offline = computed(
    () => this.connectivity.startedOffline() && !this.meStore.loaded(),
  );
  /** Catégorie ouverte du rail : une seule à la fois. */
  protected readonly open = signal<NavGroupKey | null>(null);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );

  constructor() {
    effect(() => this.navigation.enterEdition(this.editionId()));
    effect(() => {
      const edition = this.edition();
      if (edition) {
        this.context.rememberEdition(edition.id);
      }
    });
    // Rail repositionné à chaque navigation et à l'arrivée de `/me` (rail construit avant
    // la réponse du serveur : vide, puis rempli).
    effect(() => {
      const groups = this.groups();
      const url = this.url();
      untracked(() => this.follow(groups, url));
    });
  }

  ngOnDestroy(): void {
    this.navigation.leaveEdition();
  }

  protected title(edition: { title_fr: string; title_en?: string }): string {
    return editionTitle(edition, this.language.current());
  }

  protected selectEdition(value: string): void {
    void this.router.navigate(['/editions', Number(value)]);
  }

  protected selectRole(value: string): void {
    this.navigation.selectRole((value || null) as Role | null);
  }

  /** Un clic ouvre une autre catégorie (ou referme celle-ci) ; la navigation reprend la main. */
  protected toggle(key: NavGroupKey): void {
    this.open.set(this.open() === key ? null : key);
  }

  /**
   * Ouvre la catégorie de l'écran courant. Repli indispensable : une URL hors table
   * laisserait toutes les catégories fermées, et un rail fermé ressemble à un rail vide.
   */
  private follow(groups: readonly NavGroup[], url: string): void {
    const current = this.open();
    const keep = groups.some((group) => group.key === current) ? current : null;
    this.open.set(activeGroup(groups, url) ?? keep ?? groups[0]?.key ?? null);
  }
}
