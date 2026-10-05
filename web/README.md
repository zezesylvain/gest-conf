# GEST-CONF — applications Angular

Workspace Angular 22 : `portail` (pré-rendu statique), `gestion` (servie sous `/gestion/`)
et la bibliothèque partagée `@gestconf/shared`. Voir le [README principal](../README.md)
pour le démarrage et les commandes.

- Client API : `projects/shared/src/lib/api/`, **généré** (`npm run api:generate`) — ne pas l'éditer.
- Traductions : `projects/*/src/i18n/{fr,en}.json` et `projects/shared/src/lib/i18n/{fr,en}.json`.
- Outils de test partagés : `@gestconf/shared/testing` (fichiers `*.spec.ts` uniquement).
