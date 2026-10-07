import { inject, Injectable } from '@angular/core';
import {
  Api,
  PublicBanner,
  PublicNewsItem,
  PublicSpeakers,
  PublicSponsors,
  publicBanner,
  publicNews,
  publicSpeakers,
  publicSponsors,
} from '@gestconf/shared';

/**
 * Contenus publics du lot L8 (plan L8, N5, N6, N10) : partenaires publiés, intervenants du
 * programme publié et actualités, lus au **pré-rendu** (visibles après `deploy.sh
 * --portal-only`) ; bandeau de dernière minute, lu **dans le navigateur** à chaque visite.
 * Réponses en liste blanche côté serveur : ni contact, ni montant, ni clé de compte.
 */
@Injectable({ providedIn: 'root' })
export class CommunityData {
  private readonly api = inject(Api);

  sponsors(): Promise<PublicSponsors> {
    return this.api.invoke(publicSponsors);
  }

  speakers(): Promise<PublicSpeakers> {
    return this.api.invoke(publicSpeakers);
  }

  news(): Promise<PublicNewsItem[]> {
    return this.api.invoke(publicNews);
  }

  banner(): Promise<PublicBanner> {
    return this.api.invoke(publicBanner);
  }
}
