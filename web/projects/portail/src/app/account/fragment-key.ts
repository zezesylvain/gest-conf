/**
 * Clé d'un lien reçu par e-mail, portée par le fragment (`#cle`) : jamais envoyée au
 * serveur ni dans l'en-tête Referer (plan L1 §4.11). Elle est lue puis effacée de la
 * barre d'adresse et de l'historique.
 */
export function takeFragmentKey(document: Document): string | null {
  const view = document.defaultView;
  const hash = view?.location.hash ?? '';
  if (hash.length <= 1) {
    return null;
  }
  let key: string;
  try {
    key = decodeURIComponent(hash.slice(1));
  } catch {
    key = hash.slice(1);
  }
  const location = view?.location;
  if (location) {
    view.history.replaceState(view.history.state, '', `${location.pathname}${location.search}`);
  }
  return key || null;
}
