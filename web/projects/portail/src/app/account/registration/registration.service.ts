import { inject, Injectable } from '@angular/core';
import {
  Api,
  DocumentRef,
  MyRegistration,
  OrderRequest,
  PatchedBillingIdentityRequest,
  PaymentCheck,
  PaymentStart,
  Quote,
  QuoteRequestRequest,
  registrationQuote,
  registrationsBilling,
  registrationsCancel,
  registrationsList,
  registrationsOrder,
  registrationsPay,
  registrationsPaymentCheck,
  registrationsProforma,
  registrationsProof,
  registrationsRetrieve,
} from '@gestconf/shared';

/**
 * Inscription du participant (plan L6, J13), par le client généré. Le serveur décide de tout :
 * prix (zone du profil, période du jour, code promo), quotas, fenêtre d'inscription,
 * annulation ; un paiement en ligne n'est confirmé que par la notification vérifiée du
 * fournisseur (RG-15), jamais par le retour du navigateur.
 */
@Injectable({ providedIn: 'root' })
export class RegistrationService {
  private readonly api = inject(Api);

  list(): Promise<MyRegistration[]> {
    return this.api.invoke(registrationsList, {});
  }

  get(id: number): Promise<MyRegistration> {
    return this.api.invoke(registrationsRetrieve, { registration_id: id });
  }

  quote(body: QuoteRequestRequest): Promise<Quote> {
    return this.api.invoke(registrationQuote, { body });
  }

  order(body: OrderRequest): Promise<MyRegistration> {
    return this.api.invoke(registrationsOrder, { body });
  }

  updateBilling(id: number, body: PatchedBillingIdentityRequest): Promise<MyRegistration> {
    return this.api.invoke(registrationsBilling, { registration_id: id, body });
  }

  cancel(id: number): Promise<MyRegistration> {
    return this.api.invoke(registrationsCancel, { registration_id: id });
  }

  uploadProof(id: number, file: File): Promise<MyRegistration> {
    return this.api.invoke(registrationsProof, { registration_id: id, body: { file } });
  }

  proforma(id: number): Promise<DocumentRef> {
    return this.api.invoke(registrationsProforma, { registration_id: id });
  }

  pay(id: number): Promise<PaymentStart> {
    return this.api.invoke(registrationsPay, { registration_id: id });
  }

  paymentCheck(id: number): Promise<PaymentCheck> {
    return this.api.invoke(registrationsPaymentCheck, { registration_id: id });
  }
}

/** PDF d'une pièce et QR : endpoints authentifiés (règle n° 8), liens directs. */
export function documentUrl(registrationId: number, documentId: number): string {
  return `/api/v1/registrations/${registrationId}/documents/${documentId}`;
}

export function qrUrl(registrationId: number): string {
  return `/api/v1/registrations/${registrationId}/qr`;
}

/** Inscription en cours (en attente ou confirmée) : une seule par édition (J5). */
export function isActive(registration: MyRegistration): boolean {
  return registration.status === 'pending' || registration.status === 'confirmed';
}
