import { QuestionKind, SurveyScope } from '@gestconf/shared';

/** Canaux d'une annonce (plan L8, N10), dans l'ordre des écrans. */
export const CHANNELS = ['on_news', 'on_banner', 'on_bell', 'by_email'] as const;
export type Channel = (typeof CHANNELS)[number];

export const QUESTION_KINDS: readonly QuestionKind[] = ['rating', 'single', 'multiple', 'text'];
export const SURVEY_SCOPES: readonly SurveyScope[] = ['global', 'session'];

/**
 * Choix d'une question saisis une ligne par choix, en français et en anglais (lignes
 * appariées) ; le serveur numérote les choix et revérifie leur nombre (2 à 12).
 */
export function choicesFrom(fr: string, en: string): { label_fr: string; label_en: string }[] {
  const lines = (value: string) =>
    value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  const english = lines(en);
  return lines(fr).map((label, index) => ({ label_fr: label, label_en: english[index] ?? '' }));
}
