# Guides d'utilisation de GEST-CONF

Documents de prise en main par public (plan [`L9-recette-plan.md`](../L9-recette-plan.md),
décision S11). Ils décrivent les **tâches courantes** de chaque rôle, dans l'ordre où elles se
présentent au cours d'une édition. Le détail de chaque écran (refus, cas particuliers) est
dans l'aide intégrée à la gestion, qui fait foi : chaque guide renvoie à ses fiches.

## Les guides

| Guide | Pour qui | Rôles de l'application |
|---|---|---|
| [Présidence et administration](presidence-administration.md) | Président de la conférence, administrateurs de l'édition | `CHAIR`, `ADMIN` |
| [Comité scientifique](comite-scientifique.md) | Président du comité scientifique (et Chair pour les décisions) | `SC_CHAIR` |
| [Relecteur](relecteur.md) | Membres du comité scientifique qui évaluent | `SC_MEMBER` |
| [Comité d'organisation](comite-organisation.md) | Membres du CO, une section par fonction | `OC_MEMBER` |
| [Bénévole et accueil](benevole-accueil.md) | Bénévoles, CO de l'accueil (comptoir, présences, badges), présidents de séance | `VOLUNTEER`, `OC_MEMBER`, `SESSION_CHAIR` |
| [Aide du portail (proposition)](aide-portail.md) | Auteurs et participants : texte de la page « Aide » du portail, à valider | — |
| [Formation](formation.md) | Formateurs : déroulé des ateliers sur l'édition de démonstration | — |

Les auteurs, participants et intervenants invités n'ont pas de guide propre : leur espace est
le portail (`/compte/…`), et la page « Aide » du portail leur est destinée
([`aide-portail.md`](aide-portail.md), texte à coller dans le CMS).

## L'aide intégrée à la gestion

- **Bouton « ? »** en bas à droite de chaque écran (« Aide sur cet écran ») : la fiche de
  l'écran courant, dans un tiroir.
- **Rail › Aide › Guide** (`/gestion/aide`) : le « Guide de la gestion », avec un index par
  profil, un index par écran, les fiches générales et « Imprimer le guide ».
- **Ctrl+K** (⌘K sur Mac) : recherche d'un écran par son nom ou par un mot du métier.
- Source : 53 fiches déclarées dans [`help-sheets.ts`][fiches]
  (`web/projects/gestion/src/app/help/`), textes FR et EN dans
  `web/projects/gestion/src/i18n/fr.json` et `en.json` (clés
  `gestion.help.sheets.<identifiant>`). Chaque guide se termine par la liste « Fiches d'aide
  liées » (identifiant et titre).
- Le portail n'a pas d'aide intégrée : sa page « Aide » est une page du CMS (L2).

## Conventions des guides

- **Chemins** : « Rubrique › Écran » reprend les libellés du rail de la gestion
  ([`core/navigation.ts`](../../web/projects/gestion/src/app/core/navigation.ts)) ; les
  boutons sont cités entre guillemets, tels qu'ils s'affichent en français.
- **Adresses** : dans la gestion, elles sont relatives à `/gestion/editions/<n°>/`
  (`<n°>` : identifiant de l'édition), par exemple `…/comites/invitations` ; dans le portail,
  l'espace personnel est sous `/compte/…`.
- **Droits** : le rail n'affiche que les écrans permis par vos rôles dans l'édition, et le
  serveur revérifie chaque opération (règle n° 2). Le sélecteur « Rôle actif » ne fait que
  filtrer l'affichage. Les guides décrivent les droits tels qu'on les voit : écran présent ou
  absent, bouton proposé ou non, refus du serveur.
- **Réauthentification** : les opérations sensibles ouvrent la fenêtre « Confirmez votre
  identité » (mot de passe, ou code de double authentification) quand votre dernière
  authentification date de plus de 5 minutes ; l'opération reprend ensuite d'elle-même.
- **Portail pré-rendu** : ce qui est enregistré dans la gestion (contenus, dates, programme
  publié, partenaires, actualités) n'apparaît sur le portail public qu'à la mise en ligne
  suivante, faite par l'exploitant (`deploy/deploy.sh --portal-only`). Seul le bandeau de
  dernière minute paraît aussitôt.
- « À vérifier » signale un point qui n'a pas pu être confirmé dans le code ou les tests.

## Recette, formation et exploitation

- **Cahier de recette** : [`docs/L9-cahier-de-recette.md`](../L9-cahier-de-recette.md)
  (démos A à I des bilans de lot, découpées en scénarios numérotés). Les ateliers de
  [`formation.md`](formation.md) y renvoient (« voir le cahier de recette, démo X »).
  (`docs/L9-recette.md` est le bilan du lot, précision de S10 au bilan de L9.7.)
- **Édition de démonstration** : `python manage.py seed_demo --confirm-fictitious` (édition
  `DEMO`, un compte fictif par rôle en `@fictif.invalid`, aucun e-mail reçu) ; voir
  [`formation.md`](formation.md).
- **Exploitation** (déploiement, cron, sauvegarde, mise en ligne du portail, commandes
  `manage.py` de l'exploitant) : [`docs/exploitation.md`](../exploitation.md) et
  [`deploy/README.md`](../../deploy/README.md). Les guides par rôle n'en reprennent que ce
  qu'il faut pour savoir à qui s'adresser.

## Tenir les guides à jour

- Un guide est une promesse, comme une fiche d'aide : quand un écran, un libellé ou une
  règle change, corriger dans le même commit la fiche (`help-sheets.ts` et i18n) **et** le
  guide qui la cite.
- Les guides sont courts à dessein : ils ne recopient pas les fiches, ils disent par où
  passer. Une explication détaillée va dans la fiche, pas dans le guide.
- Illustrations : S11 prévoit des guides illustrés. Les captures d'écran restent à prendre
  sur l'édition de démonstration, lors de la recette sur l'hébergement (L9.8) ; elles
  n'existent pas encore.

[fiches]: ../../web/projects/gestion/src/app/help/help-sheets.ts
