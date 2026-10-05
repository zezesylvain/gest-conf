# @gestconf/shared

Bibliothèque partagée par les applications `portail` et `gestion` (consommée depuis
les sources via l'alias `@gestconf/shared` de `tsconfig.json`) :

- `lib/api/` : client de l'API **généré** depuis `backend/schema.yml` (`npm run api:generate`) ;
- `lib/http/` : client HTTP (session Django + jeton CSRF) ;
- `lib/i18n/` : traductions FR/EN, langue active, titres de page traduits ;
- `lib/api-status/` : indicateur de disponibilité de l'API ;
- `testing.ts` : outils de test (`@gestconf/shared/testing`).
