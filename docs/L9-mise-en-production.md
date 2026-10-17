# Mise en production — check-list (lot L9, décision S13)

> **Statut** : check-list à remplir à l'étape 12 du runbook
> ([`L9-runbook-o2switch.md`](L9-runbook-o2switch.md)), rédigée le 12 octobre 2026. Elle
> reprend les quatorze points de l'annexe A5 de l'étude (« Check-list de mise en
> production ») et les complète par les points du plan L9 (S13), de la fiche
> [`L1-verifications-o2switch.md`](L1-verifications-o2switch.md) et de la revue
> [`L9-revue-securite.md`](L9-revue-securite.md). **Aucune ligne n'est encore cochée.**
>
> **L'ouverture de l'appel à communications est une décision du commanditaire, prise sur
> cette check-list** (§4). Ni l'équipe ni l'opérateur ne la prennent. Chaque ligne est soit
> faite, preuve à l'appui, soit acceptée par écrit par le commanditaire (dérogation motivée,
> datée) avant cette décision.

## Mode d'emploi

- **Preuve attendue** : sortie de commande (fichier de `~/gestconf-releves/` ou extrait collé),
  capture d'écran, ou référence d'un document daté. Aucune preuve ne doit contenir de secret
  (mot de passe, clé, jeton, cookie) ni de donnée personnelle.
- **Responsable** : *opérateur* (exécute sur l'hébergement et le poste d'exploitation),
  *commanditaire* (décide, fournit, valide), *équipe* (développement, CI, documentation).
- **Statut** : `[ ]` à faire ; `[x]` fait, preuve référencée ; `[D]` dérogation écrite du
  commanditaire (référence dans la dernière colonne) ; `[-]` sans objet, justifié.
- **Bloquant** : les lignes marquées **(bloquant)** le sont par une décision déjà validée (D18,
  R3 du plan L1, notice d'information) ; les autres restent bloquantes sauf dérogation.
- `<domaine>` : domaine de production, sans `https://`. Commandes `manage.py` : session
  d'exploitation (runbook, annexe A).

## 1. Annexe A5 de l'étude

| N° | Point | Preuve attendue | Responsable | Statut | Date, référence |
|---|---|---|---|---|---|
| A5-01 | `DEBUG=False`, `ALLOWED_HOSTS`, `SECRET_KEY` spécifique | Sortie de `deploy.sh` où `check --deploy --fail-level WARNING` passe (`DEBUG` est fixé à faux dans `config/settings/prod.py`) ; test de fumée « URL inconnue -> 404 JSON » ; attestation écrite : `DJANGO_SECRET_KEY` générée pour la production seule, `DJANGO_ALLOWED_HOSTS` = `<domaine>` | opérateur | [ ] | |
| A5-02 | HTTPS actif, HSTS, redirections | Tests de fumée : « HSTS », « http:// redirige vers https:// (301 ou 308) », « Django voit la requête en HTTPS (secure=true) » ; certificat AutoSSL valide (capture cPanel, date d'expiration) | opérateur | [ ] | |
| A5-03 | Migrations appliquées, comptes administrateurs créés par commande | `python manage.py migrate --check` en code 0 ; sorties de `create_conference` et `create_edition --admin-email … --current` (« Rôle ADMIN attribué » ou « Invitation ADMIN envoyée ») ; administrateurs enrôlés en 2FA, recommandée même quand elle est optionnelle (T1) (capture « Membres et rôles ») | opérateur ; commanditaire (désigne les administrateurs) | [ ] | |
| A5-04 | Rôles et grilles de l'édition configurés | Captures « Membres et rôles » (Chair, CS, CO par fonction, signataire) et de la grille (somme des poids = 100, RG-05) ; grille et pondérations définitives (question ouverte de l'étude §15) | commanditaire | [ ] | |
| A5-05 | E-mails : SPF, DKIM, DMARC valides, test d'envoi | Enregistrements DNS du domaine d'envoi ; `python manage.py send_test_email <adresse>` puis en-têtes reçus `spf=pass`, `dkim=pass`, `dmarc=pass` ; `python manage.py outbox --limit 5` (statut `sent`) ; runbook 4.3 | commanditaire (DNS, fournisseur) ; opérateur (test) | [ ] | |
| A5-06 | Paiement : clés de production, notification vérifiée, test réel de petit montant | Attestation (sans valeur) : `GESTCONF_PAYMENT_PROVIDER=cinetpay`, clés de production, `CINETPAY_SANDBOX=false`, `GESTCONF_ALLOW_FAKE_PAYMENTS` absent ; paiement réel de petit montant sur l'édition réelle : statut confirmé par l'interrogation du prestataire (RG-15), facture émise, notification reçue sur `/api/v1/payments/webhook/cinetpay` ; avoir si remboursement. Sans paiement en ligne à l'ouverture : `[-]` avec la décision écrite (paiement manuel seul) ; question Q7 ouverte (carte bancaire absente de l'API v1 de CinetPay) | commanditaire (contrat, montant) ; opérateur | [ ] | |
| A5-07 | Cron configuré et battement de cœur vérifié | Capture de la crontab cPanel (onze lignes de `deploy/cron.sh`) ; relevé des 48 heures du runbook (étape 4) : `jobs: ok`, `backup: ok`, aucun passage en erreur | opérateur | [ ] | |
| A5-08 | Sauvegarde automatique et **restauration testée** **(bloquant, D18)** | Runbook étape 5 : date, dump, durée du transfert et de `restore.sh` (< 4 h), résultat conforme ; seconde restauration de l'étape 10 ; fiche H-9 ; journal du cron de copie du poste (`pull-backups.sh`) des trois dernières nuits | opérateur | [ ] | |
| A5-09 | Dossier de fichiers privés hors racine web, droits restreints | `stat -c "%a %n"` : `.env` en 600, `var/backups` en 700, `var/files` en 700 (runbook étape 8) ; `curl -s -o /dev/null -w '%{http_code}' https://<domaine>/api/v1/submissions/1/file/content` sans session : 401 ; `GESTCONF_FILES_DIR` hors de `public_html` | opérateur | [ ] | |
| A5-10 | Test d'accès : un relecteur ne peut lire ni l'identité des auteurs ni une soumission non affectée | CI verte au commit déployé (matrice des droits `tests/test_matrix.py`, tests de fuite `apps/reviews/tests/test_leaks.py`) : lien vers l'exécution ; scénario correspondant de la démo E joué sur l'hébergement (cahier de recette) | équipe (CI) ; commanditaire (recette) | [ ] | |
| A5-11 | Supervision et alertes actives | Sondes externes en service (capture, runbook étape 11) et alerte de test reçue ; `GESTCONF_OPERATORS` renseigné et `sendtestemail --admins` reçu (runbook 4.3) | opérateur | [ ] | |
| A5-12 | Pages légales publiées (mentions, confidentialité, cookies) | Texte définitif validé par le commanditaire à partir de la trame [`pages-legales-trame.md`](pages-legales-trame.md) ; pages du CMS publiées en FR et EN (`/fr/p/<slug>/`, `/en/p/<slug>/`), liées au pied de page, après `deploy.sh --portal-only` : adresses et captures | commanditaire (texte) ; opérateur (publication) | [ ] | |
| A5-13 | Test de charge exécuté sur l'hébergement réel | Runbook étape 7 : ligne `Verdict : OBJECTIF ATTEINT`, requêtes les plus lentes, erreurs, mesures R14 ; base revenue à l'état antérieur | opérateur ; équipe (analyse) | [ ] | |
| A5-14 | Documentation d'exploitation remise | [`exploitation.md`](exploitation.md), runbook, [`deploy/README.md`](../deploy/README.md), guides par rôle (S11, [`guides/`](guides/README.md)) ; formation faite (publics et dates, question 10 du plan L9) ; accusé de remise daté | équipe ; commanditaire (réception) | [ ] | |

## 2. Points complémentaires (plan L9, fiche o2switch, revue de sécurité)

| N° | Point | Preuve attendue | Responsable | Statut | Date, référence |
|---|---|---|---|---|---|
| C-01 | Fiche o2switch remplie (V00 à V29, M01 à M10) et décisions H-1 à H-11 validées | Fiche complétée, colonne « Validée par, date » renseignée | opérateur ; équipe et commanditaire (validation) | [ ] | |
| C-02 | IP réelle du client mesurée **(bloquant, R3 du plan L1)** | M04 et H-8 : valeur de `GESTCONF_TRUSTED_PROXY_COUNT` ; l'adresse forgée n'est jamais retenue | opérateur | [ ] | |
| C-03 | Diagnostic désactivé | M09 ; test de fumée « diagnostic désactivé (404) » au dernier déploiement | opérateur | [ ] | |
| C-04 | Revue de sécurité close | Aucun constat élevé ouvert ; R1b vérifié (runbook étape 6 : 413, espace inchangé) ; analyse ZAP passive traitée, R16 relevé (étape 8) ; contrôles de la revue §7 faits | équipe ; opérateur | [ ] | |
| C-05 | Recette des démos A à I | Cahier de recette joué et signé par le commanditaire ; aucune anomalie bloquante ouverte | commanditaire | [ ] | |
| C-06 | Base propre avant la première donnée réelle | Runbook 10.4 : `False 0` (aucune donnée fictive), `migrate --check` en code 0, `check_integrity` sans anomalie ; portail sans page de démonstration ; `GESTCONF_ALLOW_FAKE_PAYMENTS` et `GESTCONF_DIAGNOSTICS` absents du `.env` | opérateur | [ ] | |
| C-07 | Clés conservées hors hébergement, séparément des sauvegardes | Attestation : `GESTCONF_MFA_ENCRYPTION_KEYS`, `DJANGO_SECRET_KEY` et, le cas échéant, `GESTCONF_SIGNING_ENCRYPTION_KEYS` dans le coffre du commanditaire ; détenteurs nommés | commanditaire | [ ] | |
| C-08 | Copie hors hébergement automatique | Crontab du poste de l'opérateur (heure entre 2 h 07 et 3 h 17, heure du serveur) ; trois sorties consécutives conformes de `pull-backups.sh` | opérateur | [ ] | |
| C-09 | Objectifs de reprise validés | Accord écrit du commanditaire sur la perte maximale de 24 h et le rétablissement sous 4 h (hypothèse 3 du plan L9) | commanditaire | [ ] | |
| C-10 | Édition réelle prête | Édition publiée et courante (`set_edition_status <code> published --reason …`, `set_current_edition <code>`) ; calendrier, thématiques, types, niveau de double aveugle (gelé dès la première soumission, RG-19) vérifiés dans la gestion | commanditaire ; opérateur | [ ] | |
| C-11 | Portail publié pour l'édition réelle | `deploy/deploy.sh --portal-only` ; tests de fumée complets (pages pré-rendues, `sitemap.xml`, ligne `Sitemap:` de `robots.txt`) | opérateur | [ ] | |
| C-12 | CI verte au commit déployé | Lien vers l'exécution : tests, parcours de bout en bout, `pip-audit`, `npm audit` ; seuil de couverture et audit d'accessibilité une fois l'étape L9.6 livrée | équipe | [ ] | |

## 3. Points dépendant du commanditaire

| N° | Point | Preuve attendue | Responsable | Statut | Date, référence |
|---|---|---|---|---|---|
| P-01 | Pages légales : texte définitif (décision S14) | Textes FR et EN validés et datés (voir A5-12) ; responsable du traitement, contact et durées renseignés | commanditaire | [ ] | |
| P-02 | Notice d'information définitive **(bloquant : la version provisoire `2026-10-v0` ne doit pas ouvrir l'appel, `apps/accounts/consents.py`)** | Texte définitif fourni ; nouvelle version déployée par l'équipe (`CURRENT_TEXT_VERSIONS` côté serveur et `PRIVACY_NOTICE_VERSION` côté portail, alignés) | commanditaire (texte) ; équipe (code) | [ ] | |
| P-03 | SPF, DKIM, DMARC du domaine d'envoi | Enregistrements DNS publiés ; résultat `pass` (voir A5-05) | commanditaire | [ ] | |
| P-04 | Clés de paiement de production et paiement réel de petit montant | Contrat CinetPay actif, clés transmises à l'opérateur par un canal sûr ; paiement réel réussi (voir A5-06) | commanditaire | [ ] | |
| P-05 | Quota du fournisseur d'e-mails | Offre souscrite et quota relevés ; `GESTCONF_EMAIL_MAX_PER_HOUR` aligné (les envois groupés en prennent la moitié, RG-22) ; volume attendu des annonces | commanditaire ; opérateur | [ ] | |
| P-06 | Durées de conservation (D15) | Durées validées par écrit ; `GESTCONF_RETENTION_ENFORCED=true` posé, ou décision écrite de rester en simulation ; durées reportées dans la politique de confidentialité | commanditaire ; opérateur | [ ] | |
| P-07 | Formalités de protection des données | Déclaration ou autorisation auprès de l'ARTCI (loi n° 2013-450) et, si le RGPD s'applique, analyse correspondante : références (formalités exactes à établir par le commanditaire, non vérifiées par l'équipe) | commanditaire | [ ] | |
| P-08 | Procédure de vérification d'identité | Procédure écrite pour `reset_mfa`, l'export et l'anonymisation sur demande (question ouverte de l'étude §17.10) | commanditaire | [ ] | |
| P-09 | Hypothèses du plan L9 confirmées ou remplacées | Réponses aux questions du §10 du plan (opérateur, copie hors hébergement, Sentry, anti-robots, antivirus, déploiement continu…) ou maintien écrit des hypothèses | commanditaire | [ ] | |
| P-10 | o2switch informé et joignable | Références des tickets (test de charge, ZAP) ; contact du support pour les incidents | commanditaire ; opérateur | [ ] | |
| P-11 | 2FA : optionnelle ou imposée (décision T1) | Décision écrite : `GESTCONF_MFA_ENFORCED` absent ou `false` (2FA optionnelle, risque R18 de la revue de sécurité accepté) ou `true` (imposée aux rôles de gestion) ; valeur relevée dans le `.env` ; pages légales (§2.8) alignées sur la décision | commanditaire ; opérateur | [ ] | |

## 4. Décision d'ouverture de l'appel

L'ouverture de l'appel à communications est **décidée par le commanditaire**, au vu de cette
check-list. Dès la première soumission, le niveau de double aveugle et le code de l'édition
sont gelés (RG-19 ; seul un `ADMIN` les change ensuite, avec un motif journalisé) ; les données
réelles commencent, et la sauvegarde quotidienne, sa copie hors
hébergement et la surveillance deviennent des obligations d'exploitation (voir
[`exploitation.md`](exploitation.md)).

| Décision | Date | Nom et fonction | Lignes en dérogation (`[D]`) et réserves |
|---|---|---|---|
| Ouverture de l'appel : oui / non | | | |
