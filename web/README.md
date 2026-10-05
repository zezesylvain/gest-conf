# GEST-CONF — applications Angular

Workspace Angular 22 : `portail` (pré-rendu statique), `gestion` (servie sous `/gestion/`)
et la bibliothèque partagée `@gestconf/shared`. Voir le [README principal](../README.md)
pour le démarrage et les commandes.

- Client API : `projects/shared/src/lib/api/`, **généré** (`npm run api:generate`) — ne pas l'éditer.
- Traductions : `projects/*/src/i18n/{fr,en}.json` et `projects/shared/src/lib/i18n/{fr,en}.json`.
- Outils de test partagés : `@gestconf/shared/testing` (fichiers `*.spec.ts` uniquement).
- `robots.txt` : `projects/portail/public/robots.txt`, copié à la racine du build du portail
  (exclut `/api/`, `/gestion/` et `/compte`).
- Kit d'interface : **Angular Material 22** (D9). Jetons `--gc-*` :
  `projects/shared/src/lib/ui-kit/_tokens.scss` (styles initiaux des deux applications) ; thème :
  `projects/shared/src/lib/ui-kit/theme.scss`, global dans la gestion, **feuille séparée**
  `gc-theme.css` (non injectée, sans empreinte) dans le portail, chargée par la coque de `/compte`
  (`projects/portail/src/app/account/theme.ts`). La CI vérifie son absence des pages publiques.
- Session et API : `provideGestconfApi()` (intercepteurs : langue, session et CSRF, erreurs
  normalisées en `GcApiError`), façade `AuthApi` des endpoints allauth (écrite à la main, figée
  par les tests de contrat du backend), stores `SessionStore` et `MeStore`, garde `authGuard`,
  `safeNext` (redirections ouvertes). Les composants n'appellent jamais `HttpClient` : client
  généré (`Api.invoke`) ou `AuthApi`.
- Espace compte du portail : `/compte/*` (`projects/portail/src/app/account/`), rendu dans le
  navigateur, `noindex`.
- npm : modifier `package-lock.json` avec **npm 11.19.0** (`packageManager`) ; npm 10 retire les
  champs `libc` du verrou.
- Budgets de production (`angular.json`, tailles brutes, 1 kB = 1 000 octets) :
  - **portail** (plan §10.5, R15) : `initial` 365 kB en avertissement et 380 kB en erreur
    (mesure de L1.4 : 356,6 kB, 102,6 kB transférés ; L1.1 : 297,07 kB). La hausse vient du
    découpage d'esbuild : le code d'`@angular/core` utilisé par l'espace compte (Material, coque)
    est placé dans un morceau importé par `main` (écart à valider, plan §16). Feuille globale
    `styles` 4 kB et 8 kB (567 octets mesurés) : ce budget fait échouer le build si le thème
    Material est injecté dans les styles initiaux du portail. On ne relève un budget qu'après une
    nouvelle mesure, en le justifiant dans la PR ;
  - **gestion** : budgets génériques (500 kB / 1 MB) ; mesure avec le thème Material global
    (L1.4) : 279,2 kB, dont 7,7 kB de styles. À resserrer après les écrans de L1.7.
