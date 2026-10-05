import { HttpErrorResponse } from '@angular/common/http';

/** Erreurs de champ : nom du champ → messages (format DRF ; « param » d'allauth). */
export type FieldErrors = Record<string, string[]>;

/** Clé des erreurs qui ne portent sur aucun champ (DRF : non_field_errors). */
export const NON_FIELD_ERRORS = 'non_field_errors';

/**
 * Erreur normalisée de l'API (plan L1 §10.1), quel que soit son format d'origine :
 * - API métier DRF : `{code, message, fields}` ;
 * - allauth headless : `{status, errors: [{code, message, param}]}`.
 *
 * `code` est un code du catalogue `ErrorCode` (DRF) ou un code d'allauth
 * (`email_password_mismatch`…), traduit par l'interface sous `shared.errors.<code>` ;
 * `message` est le message du serveur, affiché en repli. `body` garde le corps brut :
 * pour allauth, un 401 fait partie du protocole et porte les flux (`data.flows`).
 */
export class GcApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly fields: FieldErrors = {},
    readonly body: unknown = null,
  ) {
    super(message);
    this.name = 'GcApiError';
  }
}

interface AllauthErrorItem {
  code?: string;
  message?: string;
  param?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asMessages(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value.map((item) => String(item));
  }
  return value === undefined || value === null ? [] : [String(value)];
}

/** Code générique selon le statut HTTP, quand le corps n'en porte pas. */
export function fallbackCode(status: number): string {
  switch (status) {
    case 0:
      return 'network_error';
    case 400:
      return 'bad_request';
    case 401:
      return 'not_authenticated';
    case 403:
      return 'permission_denied';
    case 404:
      return 'not_found';
    case 409:
      return 'conflict';
    case 429:
      return 'throttled';
    default:
      return status >= 500 ? 'server_error' : 'bad_request';
  }
}

/**
 * Corps d'erreur exploitable. Une requête attendue sans corps JSON (DELETE → 204 : le
 * client généré demande du texte) reçoit son erreur en **chaîne** : on la relit en JSON,
 * sinon le code et les messages du serveur seraient perdus (« Requête invalide »).
 */
function parsedBody(body: unknown): unknown {
  if (typeof body !== 'string' || !body.trim().startsWith('{')) {
    return body;
  }
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return body;
  }
}

/** Convertit toute erreur HTTP (ou autre) en `GcApiError`. */
export function toApiError(error: unknown): GcApiError {
  if (error instanceof GcApiError) {
    return error;
  }
  if (!(error instanceof HttpErrorResponse)) {
    return new GcApiError(
      0,
      'network_error',
      error instanceof Error ? error.message : String(error),
    );
  }
  const body: unknown = parsedBody(error.error);
  const status = error.status;

  // DRF : {code, message, fields}.
  if (isRecord(body) && typeof body['code'] === 'string') {
    const fields: FieldErrors = {};
    if (isRecord(body['fields'])) {
      for (const [name, messages] of Object.entries(body['fields'])) {
        fields[name] = asMessages(messages);
      }
    }
    return new GcApiError(status, body['code'], String(body['message'] ?? ''), fields, body);
  }

  // allauth : {status, errors: [{code, message, param}]} ou {status, data, meta}.
  if (isRecord(body) && typeof body['status'] === 'number') {
    const items = Array.isArray(body['errors']) ? (body['errors'] as AllauthErrorItem[]) : [];
    const fields: FieldErrors = {};
    for (const item of items) {
      const name = item.param || NON_FIELD_ERRORS;
      (fields[name] ??= []).push(item.message ?? '');
    }
    const first = items[0];
    return new GcApiError(
      status,
      first?.code ?? fallbackCode(status),
      first?.message ?? '',
      fields,
      body,
    );
  }

  return new GcApiError(status, fallbackCode(status), error.message, {}, body);
}
