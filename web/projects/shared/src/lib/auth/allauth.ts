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
  data?: {
    user?: AllauthUser;
    flows?: AllauthFlow[];
    email?: string;
  };
  meta?: { is_authenticated?: boolean; is_authenticating?: boolean };
  errors?: AllauthErrorItem[];
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
  const flows = body?.data?.flows ?? [];
  const pending =
    flows.find((flow) => flow.is_pending && PENDING_FLOWS.includes(flow.id)) ??
    // « reauthenticate » est signalé sans is_pending (401 sur une action protégée).
    (httpStatus === 401 && body?.meta?.is_authenticated
      ? flows.find((flow) => PENDING_FLOWS.includes(flow.id))
      : undefined);
  return {
    status: body?.status ?? httpStatus,
    authenticated: body?.meta?.is_authenticated === true,
    user: body?.data?.user ?? null,
    pendingFlow: (pending?.id as PendingFlow | undefined) ?? null,
    errors: body?.errors ?? [],
  };
}
