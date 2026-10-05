# GEST-CONF — applications Angular

Workspace Angular 22 : `portail` (pré-rendu statique), `gestion` (servie sous `/gestion/`)
et la bibliothèque partagée `@gestconf/shared`. Voir le [README principal](../README.md)
pour le démarrage et les commandes.

- Client API : `projects/shared/src/lib/api/`, **généré** (`npm run api:generate`) — ne pas l'éditer.
- Traductions : `projects/*/src/i18n/{fr,en}.json` et `projects/shared/src/lib/i18n/{fr,en}.json`.
- Outils de test partagés : `@gestconf/shared/testing` (fichiers `*.spec.ts` uniquement).
- `robots.txt` : `projects/portail/public/robots.txt`, copié à la racine du build du portail
  (exclut `/api/`, `/gestion/` et `/compte`).
- Budgets de production (`angular.json`, tailles brutes, 1 kB = 1 000 octets) :
  - **portail** (plan §10.5, R15) : `initial` 312 kB en avertissement et 327 kB en erreur,
    soit la mesure de L1.1 (297,07 kB) + 5 % et + 10 % ; feuille globale `styles` 4 kB et 8 kB
    (mesurée à 417 octets). Ce second budget fait échouer le build si un thème Material est
    injecté dans les styles initiaux du portail. On ne relève un budget qu'après une nouvelle
    mesure, en le justifiant dans la PR ;
  - **gestion** : budgets génériques (500 kB / 1 MB) jusqu'à la mesure qui suivra l'ajout du
    thème Material global en L1.4.
