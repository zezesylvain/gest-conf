/**
 * Note pondérée **indicative**, calculée dans le navigateur pendant la saisie (plan L4 §5) ;
 * le serveur la recalcule à chaque enregistrement et fait foi (H4). Même formule :
 * `(Σ poids × note / Σ poids − min) / (max − min) × 100`, sur les critères notés ; un critère
 * facultatif non noté est exclu, un critère obligatoire non noté rend la note indéfinie.
 * Arrondi à 2 décimales, demi supérieur.
 */
export interface ScoredCriterion {
  code: string;
  weight: string | number;
  is_required?: boolean;
}

export function weightedScore(
  criteria: readonly ScoredCriterion[],
  values: Readonly<Record<string, string | number | null | undefined>>,
  scaleMin: number,
  scaleMax: number,
): number | null {
  const scored: [number, number][] = [];
  for (const criterion of criteria) {
    const raw = values[criterion.code];
    const value = raw === null || raw === undefined || raw === '' ? null : Number(raw);
    if (value === null || Number.isNaN(value)) {
      if (criterion.is_required !== false) {
        return null;
      }
      continue;
    }
    scored.push([Number(criterion.weight), value]);
  }
  const total = scored.reduce((sum, [weight]) => sum + weight, 0);
  if (!scored.length || total <= 0 || scaleMax <= scaleMin) {
    return null;
  }
  const mean = scored.reduce((sum, [weight, value]) => sum + weight * value, 0) / total;
  const score = ((mean - scaleMin) / (scaleMax - scaleMin)) * 100;
  // Demi supérieur, à l'abri des erreurs d'arrondi binaires (3,555 → 3,56).
  return Math.round((score + Number.EPSILON) * 100) / 100;
}
