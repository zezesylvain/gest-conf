import {
  CategoryRef,
  DocumentKind,
  OrderMethod,
  PaymentMethod,
  PaymentProvider,
  PaymentStatus,
  Period,
  RegistrationStatus,
  Zone,
} from '@gestconf/shared';

/** Statuts d'une inscription (plan L6, J3), dans l'ordre du workflow. */
export const REGISTRATION_STATUSES: readonly RegistrationStatus[] = [
  'pending',
  'confirmed',
  'cancelled',
  'expired',
];

/** Moyens de paiement d'une inscription (J4, J7) ; `free` et `waiver` sans encaissement. */
export const PAYMENT_METHODS: readonly PaymentMethod[] = [
  'online',
  'transfer',
  'onsite',
  'free',
  'waiver',
];

/** Moyens qu'une commande peut choisir (saisie par le CO comprise). */
export const ORDER_METHODS: readonly OrderMethod[] = ['online', 'transfer', 'onsite'];

export const PAYMENT_STATUSES: readonly PaymentStatus[] = [
  'initiated',
  'pending',
  'succeeded',
  'failed',
  'cancelled',
];

export const PAYMENT_PROVIDERS: readonly PaymentProvider[] = ['manual', 'fake', 'cinetpay'];

export const DOCUMENT_KINDS: readonly DocumentKind[] = ['invoice', 'credit_note', 'proforma'];

/** Grille des tarifs (J2) : périodes en colonnes, zones en lignes. */
export const PERIODS: readonly Period[] = ['early', 'regular', 'onsite'];
export const ZONES: readonly Zone[] = ['local', 'international'];

/** Libellé bilingue dans la langue de l'interface, le français à défaut d'anglais. */
export function label(item: { label_fr: string; label_en?: string }, lang: string): string {
  return (lang === 'en' && item.label_en) || item.label_fr;
}

export function categoryLabel(category: CategoryRef, lang: string): string {
  return label(category, lang);
}

/** Date du jour au format d'un champ `date` (`AAAA-MM-JJ`), dans le fuseau du navigateur. */
export function today(): string {
  const now = new Date();
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}
