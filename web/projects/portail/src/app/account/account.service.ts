import { inject, Injectable } from '@angular/core';
import {
  AcceptedRole,
  Api,
  ConsentRecord,
  invitationAccept,
  invitationDecline,
  invitationLinkEmail,
  InvitationLookup,
  invitationLookup,
  meConsentsCreate,
  meProfile,
  meProfileUpdate,
  meTotpQr,
  PatchedProfileRequest,
  Profile,
} from '@gestconf/shared';

/** Données de l'espace compte (client généré, plan L1 §10.1 : pas de HttpClient direct). */
@Injectable({ providedIn: 'root' })
export class AccountService {
  private readonly api = inject(Api);

  profile(): Promise<Profile> {
    return this.api.invoke(meProfile);
  }

  updateProfile(body: PatchedProfileRequest): Promise<Profile> {
    return this.api.invoke(meProfileUpdate, { body });
  }

  /** QR code du secret TOTP en attente (data:image/svg+xml), après `AuthApi.totpSetup()`. */
  async totpQrCode(): Promise<string> {
    return (await this.api.invoke(meTotpQr)).qr_code;
  }

  /** Prise de connaissance de la notice d'information (première connexion). */
  acknowledgePrivacyNotice(): Promise<ConsentRecord> {
    return this.api.invoke(meConsentsCreate, {
      body: { kind: 'privacy_notice', granted: true, source: 'first_login' },
    });
  }

  // --- Invitations (plan L1 §5.7, RG-20) -------------------------------------------------

  lookupInvitation(token: string): Promise<InvitationLookup> {
    return this.api.invoke(invitationLookup, { body: { token } });
  }

  declineInvitation(token: string): Promise<void> {
    return this.api.invoke(invitationDecline, { body: { token } });
  }

  acceptInvitation(token: string): Promise<AcceptedRole> {
    return this.api.invoke(invitationAccept, { body: { token } });
  }

  /** Lien de liaison reçu à l'adresse invitée (`#lier=…`) : réauthentification récente. */
  acceptInvitationLink(link: string): Promise<AcceptedRole> {
    return this.api.invoke(invitationAccept, { body: { link } });
  }

  /** Envoie un lien de confirmation à l'adresse invitée (RG-20, D6 (a)). */
  requestInvitationLink(token: string): Promise<void> {
    return this.api.invoke(invitationLinkEmail, { body: { token } });
  }
}
