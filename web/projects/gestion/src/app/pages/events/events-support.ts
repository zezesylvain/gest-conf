import { MatDialog } from '@angular/material/dialog';
import {
  CertificateNature,
  ConfirmDialog,
  ConfirmDialogData,
  ConfirmDialogResult,
  DocumentNature,
  LetterStatus,
} from '@gestconf/shared';
import { TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { ADMITTED, DeskResult } from '../../core/checkin-desk';

/** Natures d'attestation (K9) puis lettre (K12), dans l'ordre des écrans. */
export const CERTIFICATE_NATURES: readonly CertificateNature[] = [
  'participation',
  'presentation',
  'review',
];
export const DOCUMENT_NATURES: readonly DocumentNature[] = [...CERTIFICATE_NATURES, 'letter'];
export const LETTER_STATUSES: readonly LetterStatus[] = [
  'requested',
  'issued',
  'refused',
  'revoked',
];

/** Ton d'un résultat de pointage : admis, à signaler (déjà pointé), refusé. */
export function outcomeTone(outcome: DeskResult['outcome']): 'ok' | 'warn' | 'ko' {
  if (outcome === 'checked_in') return 'ok';
  if (ADMITTED.includes(outcome)) return 'warn';
  return 'ko';
}

/**
 * Confirmation d'une action journalisée, avec motif si `reason` (révocation, refus,
 * correction). Les textes sont sous `<prefix>.title`, `.message`, `.confirm`, `.reason`.
 */
export async function confirmAction(
  dialog: MatDialog,
  translate: TranslateService,
  prefix: string,
  params: Record<string, unknown> = {},
  reason = false,
): Promise<ConfirmDialogResult | undefined> {
  const data: ConfirmDialogData = {
    title: translate.instant(`${prefix}.title`, params),
    message: translate.instant(`${prefix}.message`, params),
    confirmLabel: translate.instant(`${prefix}.confirm`, params),
    reasonLabel: reason ? translate.instant(`${prefix}.reason`) : undefined,
  };
  const ref = dialog.open<ConfirmDialog, ConfirmDialogData, ConfirmDialogResult>(ConfirmDialog, {
    data,
    width: '32rem',
  });
  return firstValueFrom(ref.afterClosed());
}

/** Préférences du poste d'accueil (`localStorage`, accès protégé : navigation privée). */
const DEVICE_KEY = 'gc.gestion.checkin.device';
const SESSION_KEY = 'gc.gestion.checkin.session';
const SESSIONS_KEY = 'gc.gestion.checkin.sessions';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) {
      localStorage.removeItem(key);
    } else {
      localStorage.setItem(key, value);
    }
  } catch {
    // Préférence non retenue.
  }
}

/** Nom du poste, repris dans chaque pointage (« appareil », K4) ; 64 caractères au plus. */
export function deviceName(): string {
  const stored = read(DEVICE_KEY);
  if (stored) return stored;
  const name = `gc-${Math.random().toString(36).slice(2, 6)}`;
  write(DEVICE_KEY, name);
  return name;
}

export function rememberDeviceName(name: string): void {
  write(DEVICE_KEY, name.trim().slice(0, 64) || null);
}

/** Session publiée gardée pour le mode « session » hors ligne (titres seulement). */
export interface SessionChoice {
  id: number;
  title_fr: string;
  title_en: string;
  starts_at: string;
}

export function savedSessions(editionId: number): SessionChoice[] {
  try {
    const value = JSON.parse(read(`${SESSIONS_KEY}.${editionId}`) ?? '[]');
    return Array.isArray(value) ? (value as SessionChoice[]) : [];
  } catch {
    return [];
  }
}

export function saveSessions(editionId: number, sessions: SessionChoice[]): void {
  write(`${SESSIONS_KEY}.${editionId}`, JSON.stringify(sessions));
}

export function savedSession(editionId: number): number | null {
  const value = Number(read(`${SESSION_KEY}.${editionId}`));
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function saveSession(editionId: number, sessionId: number | null): void {
  write(`${SESSION_KEY}.${editionId}`, sessionId === null ? null : String(sessionId));
}

/** Titre bilingue dans la langue de l'interface, le français à défaut. */
export function title(item: { title_fr: string; title_en?: string }, lang: string): string {
  return (lang === 'en' && item.title_en) || item.title_fr;
}
