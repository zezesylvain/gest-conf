import { LogoSize, SponsorLevel, SponsorStatus } from '@gestconf/shared';

/** Catalogues fermés du serveur (plan L8, N5), dans l'ordre des écrans. */
export const SPONSOR_STATUSES: readonly SponsorStatus[] = [
  'prospect',
  'agreed',
  'received',
  'declined',
];
export const LOGO_SIZES: readonly LogoSize[] = ['small', 'medium', 'large'];

/** Logo : PNG, JPEG ou WebP de 5 Mo au plus ; le serveur revérifie le type par le contenu. */
export const LOGO_ACCEPT = 'image/png,image/jpeg,image/webp';
export const LOGO_MAX_BYTES = 5 * 1024 * 1024;

export function levelName(level: SponsorLevel | undefined, lang: string): string {
  if (!level) return '';
  return (lang === 'en' && level.name_en) || level.name_fr;
}
