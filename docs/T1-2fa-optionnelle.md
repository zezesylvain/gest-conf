# Évolution T1 — Double authentification optionnelle : décision et bilan

Demande du commanditaire, 14 octobre 2026 : « il faut rendre optionnelle la double
authentification ». Le changement touche aux permissions et revient sur des décisions
validées (D2 et D3 du lot L1, H2 du lot L4, K1 et K18 du lot L7) : il a été proposé avec son
impact sur la sécurité, puis **validé le 14 octobre 2026** (réponse « 1 » : 2FA optionnelle par
défaut, pour tous les rôles). Il est reporté dans l'étude, **§26** (version 1.10).

## 1. Décision

**T1** — La double authentification (TOTP d'`allauth.mfa`, codes de secours) est
**optionnelle par défaut** pour tous les rôles. Le paramètre d'hébergement
`GESTCONF_MFA_ENFORCED` (faux par défaut) l'**impose** de nouveau aux rôles de
`MFA_REQUIRED_ROLES` (`ADMIN`, `CHAIR`, `SC_CHAIR`, `OC_MEMBER`, `SC_MEMBER`, `VOLUNTEER`,
`SIGNATORY`), exactement comme avant. Le choix en production revient au commanditaire
(check-list de mise en production, P-11).

## 2. Comportement

| Situation | 2FA optionnelle (défaut) | 2FA imposée (`GESTCONF_MFA_ENFORCED=true`) |
|---|---|---|
| Rôle de gestion, 2FA non activée | gestion ouverte selon les capacités | 403 `mfa_enrollment_required` → page « Sécurité » |
| 2FA activée, session validée par le code | gestion ouverte | gestion ouverte |
| 2FA activée, session non validée (ouverte avant l'activation) | 403 `mfa_required` → code | 403 `mfa_required` → code |
| `/v1/me`, `editions[].mfa_required` | faux | vrai pour un rôle de gestion |
| Textes (tableau de bord, « Sécurité », invitation, aide) | « facultative, mais recommandée » | « obligatoire » |

À la connexion, allauth demande le code à tout compte qui a activé la 2FA, dans les deux modes.
La réauthentification des opérations sensibles (D12), le chiffrement des secrets
(`GESTCONF_MFA_ENCRYPTION_KEYS`, toujours obligatoire en production), `reset_mfa` et
`rotate_mfa_keys` sont inchangés. Aucun modèle ni aucune migration.

## 3. Sécurité

Constat **R18** de la revue de sécurité ([`L9-revue-securite.md`](L9-revue-securite.md)),
gravité moyenne, **accepté par le commanditaire** : sans 2FA, un compte de gestion n'est
protégé que par son mot de passe ; or les relecteurs lisent des travaux inédits, les bénévoles
téléchargent la liste des participants, le signataire signe les attestations et
l'administrateur paramètre tout. Le contrôle ASVS 4.3.1 n'est conforme qu'en mode imposé.

Atténuations : 2FA recommandée dans les écrans et les guides, vérifiée pour tout compte qui l'a
activée, mots de passe de 12 caractères, limitation des échecs de connexion, réauthentification
des opérations sensibles.

**Recommandation** : poser `GESTCONF_MFA_ENFORCED=true` au moins avant l'ouverture de
l'évaluation et du jour J ; à défaut, demander aux administrateurs, au signataire et aux
relecteurs de l'activer.

## 4. Ce qui a changé

- Serveur : `apps/accounts/permissions.py` (`MfaVerified`), `apps/accounts/services/access.py`
  (`mfa_protected`, `mfa_required`), `config/settings/base.py` (`GESTCONF_MFA_ENFORCED`) ;
  description de `mfa_required` au schéma OpenAPI et client régénéré.
- Écrans : tableau de bord de la gestion, fiche d'aide « Double authentification » ; page
  « Sécurité » et invitation acceptée du portail (FR et EN).
- Tests : `apps/accounts/tests/test_mfa.py` (modes optionnel et imposé),
  `tests/test_matrix.py::test_t1_two_factor_authentication_is_optional_by_default` (chaque
  rôle concerné ; les cas de D3, H2, K1 et K18 tournent en mode imposé), specs du portail,
  parcours de bout en bout (étape 17 : un CO « bénévoles » sans 2FA se connecte sans code et
  ouvre la gestion).
- Documents : étude §26 (Markdown et HTML), `CLAUDE.md`, revue de sécurité (R18), check-list
  de mise en production (P-11), guides par rôle, cahier de recette (B4), `.env.example`,
  `deploy/README.md`, `exploitation.md`, trame des pages légales (§2.8).

## 5. Revenir à la 2FA imposée

Dans le `.env` de l'hébergement : `GESTCONF_MFA_ENFORCED=true`, puis redémarrer Passenger
(`tmp/restart.txt`). Les comptes de gestion sans 2FA sont alors renvoyés vers « Sécurité » à
leur prochaine requête de gestion ; aucune donnée n'est modifiée. Penser à aligner les pages
légales (§2.8 de la trame).
