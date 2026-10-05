import { inject, Injectable } from '@angular/core';
import {
  Api,
  PublicComposition,
  publicPortalPage,
  publicPortalSite,
  PublicSite,
} from '@gestconf/shared';

/** Composition des pages et données du site (plan L2 §4), lues une fois par chargement. */
@Injectable({ providedIn: 'root' })
export class PortalData {
  private readonly api = inject(Api);
  private site$: Promise<PublicSite> | null = null;

  page(slug: string): Promise<PublicComposition> {
    return this.api.invoke(publicPortalPage, { slug });
  }

  site(): Promise<PublicSite> {
    this.site$ ??= this.api.invoke(publicPortalSite);
    return this.site$;
  }
}
