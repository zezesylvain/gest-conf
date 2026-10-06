import { inject, Injectable } from '@angular/core';
import {
  Api,
  GcApiError,
  LetterRequestRequest,
  meCertificates,
  MyCertificate,
  MyLetter,
  publicCertificateVerify,
  PublicVerification,
  registrationsLetter,
  registrationsLetterRequest,
} from '@gestconf/shared';

/**
 * Documents du participant (plan L7, K3, K9, K12) et vérification publique (K10), par le
 * client généré. Le serveur décide de tout : badge dès la confirmation, attestations émises
 * par le comité (RG-16), lettre d'invitation instruite par le comité.
 */
@Injectable({ providedIn: 'root' })
export class DocumentsService {
  private readonly api = inject(Api);

  certificates(): Promise<MyCertificate[]> {
    return this.api.invoke(meCertificates, {});
  }

  /** Dernière demande de lettre de l'inscription ; `null` s'il n'y en a pas (404). */
  async letter(registrationId: number): Promise<MyLetter | null> {
    try {
      return await this.api.invoke(registrationsLetter, { registration_id: registrationId });
    } catch (error) {
      if (error instanceof GcApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }

  requestLetter(registrationId: number, body: LetterRequestRequest): Promise<MyLetter> {
    return this.api.invoke(registrationsLetterRequest, { registration_id: registrationId, body });
  }

  /** Vérification publique ; `null` pour un code inconnu ou mal formé (même réponse 404). */
  async verify(code: string): Promise<PublicVerification | null> {
    try {
      return await this.api.invoke(publicCertificateVerify, { code });
    } catch (error) {
      if (error instanceof GcApiError && error.status === 404) {
        return null;
      }
      throw error;
    }
  }
}

/** PDF servis par des endpoints authentifiés (règle n° 8) : liens directs, même origine. */
export function badgeUrl(registrationId: number): string {
  return `/api/v1/registrations/${registrationId}/badge`;
}

export function certificatePdfUrl(certificateId: number): string {
  return `/api/v1/me/certificates/${certificateId}/pdf`;
}

export function letterPdfUrl(registrationId: number): string {
  return `/api/v1/registrations/${registrationId}/invitation-letter/pdf`;
}

/** Date civile (`2027-06-01`) dans la langue de l'interface, sans fuseau (« 1 juin 2027 »). */
export function formatDay(day: string, locale: string): string {
  const value = new Date(`${day}T00:00:00Z`);
  if (Number.isNaN(value.getTime())) {
    return day;
  }
  return new Intl.DateTimeFormat(locale, { dateStyle: 'long', timeZone: 'UTC' }).format(value);
}
