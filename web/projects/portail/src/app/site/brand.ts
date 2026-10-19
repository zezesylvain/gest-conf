/**
 * Marque de l'en-tête (décision T4, V6) : le code de l'édition, séparé de son année quand il
 * finit par elle (« ICHA2027 » → « ICHA 2027 »). Pas de champ « titre court » : à décider.
 */
export function brandName(code: string, year: number | null | undefined): string {
  const suffix = year ? String(year) : '';
  if (suffix && code.length > suffix.length && code.endsWith(suffix)) {
    return `${code.slice(0, -suffix.length).replace(/[-_\s]+$/, '')} ${suffix}`;
  }
  return code;
}
