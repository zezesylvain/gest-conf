import { inject, Injectable, signal } from '@angular/core';
import { Api, MenuLocation, PublicMenuItem, publicPortalMenu } from '@gestconf/shared';

import { SiteLanguage } from './site-pages';

/**
 * Menus du portail public (plan L2 §4), lus par la coque. Au pré-rendu, les réponses sont
 * transférées au navigateur (cache de transfert) : aucune requête n'est refaite. Les pages
 * et les données du site sont lues par `PortalData` (chargé avec les pages).
 */
@Injectable({ providedIn: 'root' })
export class PublicMenus {
  private readonly api = inject(Api);
  private readonly menus = new Map<MenuLocation, Promise<PublicMenuItem[]>>();

  menu(location: MenuLocation): Promise<PublicMenuItem[]> {
    let menu = this.menus.get(location);
    if (!menu) {
      menu = this.api.invoke(publicPortalMenu, { location }).catch(() => []);
      this.menus.set(location, menu);
    }
    return menu;
  }
}

/**
 * Contexte de la page publique affichée : langue de l'adresse et adresses de la même page
 * dans chaque langue (sélecteur de langue par liens, `hreflang`). Hors portail public
 * (espace compte), `paths` est nul.
 */
@Injectable({ providedIn: 'root' })
export class PageContext {
  readonly language = signal<SiteLanguage | null>(null);
  readonly paths = signal<Record<SiteLanguage, string> | null>(null);

  set(language: SiteLanguage, paths: Record<SiteLanguage, string>): void {
    this.language.set(language);
    this.paths.set(paths);
  }

  clear(): void {
    this.language.set(null);
    this.paths.set(null);
  }
}
