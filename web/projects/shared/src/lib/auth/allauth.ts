/**
 * Contrat des réponses d'allauth headless (client « browser »), limité aux champs
 * consommés. Figé côté serveur par les tests de contrat
 * (backend/apps/accounts/tests/test_contract.py, décision D4).
 */
export interface AllauthUser {
  id: number;
  email: string;
  display: string;
  has_usable_password: boolean;
}

export interface AllauthFlow {
  id: string;
  is_pending?: boolean;
}

export interface AllauthErrorItem {
  code: string;
  message: string;
  param?: string;
}

export interface AllauthResponse {
  status: number;
  /** Session et flux, ou contenu propre à l'endpoint (authentificateurs, adresses…). */
  data?: unknown;
  meta?: {
    is_authenticated?: boolean;
    is_authenticating?: boolean;
    /** Enrôlement TOTP (404 de `account/authenticators/totp`). */
    secret?: string;
    totp_url?: string;
  };
  errors?: AllauthErrorItem[];
}

interface AllauthSessionData {
  user?: AllauthUser;
  flows?: AllauthFlow[];
}

/** Authentificateur 2FA (`GET account/authenticators`, plan L1 §4.3). */
export interface AuthenticatorInfo {
  type: 'totp' | 'recovery_codes';
  created_at: number;
  last_used_at: number | null;
  total_code_count?: number;
  unused_code_count?: number;
}

/** Codes de secours (`GET`/`POST account/authenticators/recovery-codes`). */
export interface RecoveryCodesInfo extends AuthenticatorInfo {
  unused_codes: string[];
}

/** Secret TOTP en attente d'activation (texte, pour la saisie manuelle). */
export interface TotpSetup {
  secret: string;
  totpUrl: string;
}

/** Adresse e-mail du compte (`GET account/email`). */
export interface EmailAddressInfo {
  email: string;
  verified: boolean;
  primary: boolean;
}

/** Flux qu'une réponse 401 d'allauth peut signaler (plan L1 §4.3). */
export type PendingFlow =
  'verify_email' | 'mfa_authenticate' | 'reauthenticate' | 'mfa_reauthenticate';

/** Résultat d'un appel à allauth, succès ou refus « de protocole ». */
export interface AuthResult {
  status: number;
  authenticated: boolean;
  user: AllauthUser | null;
  /** Flux en attente (verify_email, mfa_authenticate…), ou à lancer (reauthenticate). */
  pendingFlow: PendingFlow | null;
  errors: AllauthErrorItem[];
  /** Tous les flux signalés (ex. `reauthenticate` et `mfa_reauthenticate`). */
  flows?: string[];
  /** Contenu de la réponse (`data`), propre à l'endpoint. */
  data?: unknown;
  meta?: AllauthResponse['meta'];
}

const PENDING_FLOWS: readonly string[] = [
  'verify_email',
  'mfa_authenticate',
  'reauthenticate',
  'mfa_reauthenticate',
];

export function toAuthResult(
  body: AllauthResponse | null | undefined,
  httpStatus: number,
): AuthResult {
  const sessionData = (body?.data ?? {}) as AllauthSessionData;
  const flows = Array.isArray(sessionData.flows) ? sessionData.flows : [];
  const pending =
    flows.find((flow) => flow.is_pending && PENDING_FLOWS.includes(flow.id)) ??
    // « reauthenticate » est signalé sans is_pending (401 sur une action protégée).
    (httpStatus === 401 && body?.meta?.is_authenticated
      ? flows.find((flow) => PENDING_FLOWS.includes(flow.id))
      : undefined);
  return {
    status: body?.status ?? httpStatus,
    authenticated: body?.meta?.is_authenticated === true,
    user: sessionData.user ?? null,
    pendingFlow: (pending?.id as PendingFlow | undefined) ?? null,
    errors: body?.errors ?? [],
    flows: flows.map((flow) => flow.id),
    data: body?.data,
    meta: body?.meta,
  };
}
