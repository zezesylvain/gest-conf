import { inject, Injectable } from '@angular/core';
import { Api, PublicRegistration, publicRegistration } from '@gestconf/shared';

/**
 * Catalogue public des inscriptions (plan L6, J13) : catégories, tarifs, options, dates et
 * moyens de paiement de l'édition courante. Lu au pré-rendu (page publique) et par l'espace
 * « Mon inscription » (formulaire de commande) ; ni quota restant ni donnée personnelle.
 */
@Injectable({ providedIn: 'root' })
export class RegistrationData {
  private readonly api = inject(Api);

  catalog(): Promise<PublicRegistration> {
    return this.api.invoke(publicRegistration);
  }
}
