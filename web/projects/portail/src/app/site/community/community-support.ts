/** Ancre d'une actualité sur la page « Actualités » : le bandeau de dernière minute y mène. */
export function newsAnchor(id: number): string {
  return `actualite-${id}`;
}
