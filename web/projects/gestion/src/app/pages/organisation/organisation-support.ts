import { BudgetCategory, BudgetKind, GcApiError, TaskPriority, TaskStatus } from '@gestconf/shared';

/** Colonnes du tableau des tâches, dans l'ordre (N3). */
export const TASK_STATUSES: readonly TaskStatus[] = ['todo', 'doing', 'done'];
export const TASK_PRIORITIES: readonly TaskPriority[] = ['low', 'normal', 'high'];

/** Postes du budget par nature (N4, catalogue fermé du serveur). */
export const BUDGET_CATEGORIES: Readonly<Record<BudgetKind, readonly BudgetCategory[]>> = {
  expense: [
    'venue',
    'catering',
    'travel',
    'accommodation',
    'communication',
    'printing',
    'equipment',
    'staff',
    'other_expense',
  ],
  income: ['registrations', 'sponsorship', 'grants', 'other_income'],
};

/** Pièces jointes et justificatifs acceptés par le serveur (type vérifié par contenu). */
export const ATTACHMENT_ACCEPT = 'application/pdf,image/png,image/jpeg';
export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;

/** Jour (`AAAA-MM-JJ`) au format de la langue, sans décalage de fuseau. */
export function formatDay(day: string | null | undefined, lang: string): string {
  if (!day) return '—';
  return new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'fr-FR', {
    dateStyle: 'medium',
    timeZone: 'UTC',
  }).format(new Date(`${day}T00:00:00Z`));
}

/** La ressource a changé depuis sa lecture (`If-Match` périmé, 412). */
export function isStale(error: unknown): boolean {
  return error instanceof GcApiError && error.code === 'stale_revision';
}
