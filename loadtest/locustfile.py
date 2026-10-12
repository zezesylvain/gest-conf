"""Test de charge GEST-CONF (plan L9, S5 ; étude §12) : scénarios Locust.

Cinq profils, pondérés comme un pic d'ouverture des inscriptions et de clôture de l'appel :
visiteurs (pages pré-rendues, bandeau), auteurs (brouillon, PDF, envoi), relecteurs (liste,
évaluation), participants (devis, inscription, « Mon inscription ») et comité (listes
paginées de 600 soumissions et de 1 500 inscriptions, classement, tableaux de bord).

Les comptes sont ceux de ``seed_volume`` ; leurs sessions viennent de ``loadtest_sessions``
(fichier JSON désigné par ``GESTCONF_SESSIONS``) : aucune connexion pendant le test, dont
les limites de débit par adresse IP l'arrêteraient. Mode d'emploi : ``loadtest/README.md``.

Verdict à la fin (code de sortie non nul en cas d'échec) : p95 < 500 ms et moins de 1 %
d'erreurs sur l'ensemble des requêtes, hors celles marquées « (PDF) » (génération de pièce,
exclue de l'objectif par l'étude §12) qui sont rapportées à part.
"""

from __future__ import annotations

import itertools
import json
import os
import random
import threading
import time

from locust import HttpUser, between, events, task
from locust.stats import calculate_response_time_percentile

API = "/api/v1"
P95_TARGET_MS = int(os.environ.get("GESTCONF_P95_MS", "500"))
FAILURE_TARGET = float(os.environ.get("GESTCONF_MAX_FAILURE_RATIO", "0.01"))
PDF_TAG = "(PDF)"
# Pages pré-rendues servies par Apache (absentes d'un essai local contre runserver : vide).
PAGES = [
    page
    for page in os.environ.get(
        "GESTCONF_PAGES", "/fr/,/en/,/fr/programme,/fr/inscription,/fr/partenaires"
    ).split(",")
    if page
]

_sessions: dict | None = None
_pools: dict[str, itertools.cycle] = {}
_lock = threading.Lock()


def sessions() -> dict:
    global _sessions
    if _sessions is None:
        path = os.environ.get("GESTCONF_SESSIONS")
        if not path:
            raise SystemExit("GESTCONF_SESSIONS : chemin du fichier de loadtest_sessions.")
        with open(path, encoding="utf-8") as handle:
            _sessions = json.load(handle)
    return _sessions


def next_account(persona: str) -> dict:
    """Comptes distribués à tour de rôle (un compte peut servir à plusieurs utilisateurs
    simulés si le profil en compte plus que de comptes)."""
    with _lock:
        if persona not in _pools:
            accounts = sessions()["personas"].get(persona) or []
            if not accounts:
                raise SystemExit(f"Aucun compte « {persona} » dans le fichier de sessions.")
            _pools[persona] = itertools.cycle(accounts)
        return next(_pools[persona])


def tiny_pdf(label: str) -> bytes:
    """PDF d'une page, valide (table des références exacte), sans dépendance."""
    stream = f"BT /F1 12 Tf 72 720 Td (Test de charge {label}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(output)


class Visitor(HttpUser):
    """Visiteur anonyme : pages pré-rendues, bandeau et édition courante. Comme un navigateur,
    il garde ces deux réponses le temps de leur ``Cache-Control`` (60 s et 300 s)."""

    weight = 50
    wait_time = between(2, 8)

    def on_start(self) -> None:
        self.fetched: dict[str, float] = {}

    def cached_get(self, path: str, max_age: int, name: str) -> None:
        now = time.monotonic()
        if now - self.fetched.get(path, -max_age) >= max_age:
            self.client.get(path, name=name)
            self.fetched[path] = now

    @task(4)
    def page(self) -> None:
        if PAGES:
            self.client.get(random.choice(PAGES), name="portail : page pré-rendue")
        # Chaque page lit le bandeau dans le navigateur, puis l'édition courante.
        self.cached_get(f"{API}/public/portal/banner", 60, "portail : bandeau")
        self.cached_get(f"{API}/public/editions/current", 300, "portail : édition courante")

    @task(1)
    def registration_page(self) -> None:
        self.client.get(f"{API}/public/registration", name="portail : tarifs d'inscription")


class Persona(HttpUser):
    """Utilisateur connecté par une session pré-établie (cookies et jeton CSRF)."""

    abstract = True
    persona = ""
    wait_time = between(3, 10)

    def on_start(self) -> None:
        data = sessions()
        self.account = next_account(self.persona)
        self.editions = data["editions"]
        self.client.cookies.set(data["cookies"]["session"], self.account["session"])
        self.client.cookies.set(data["cookies"]["csrf"], self.account["csrf_cookie"])
        # Le contrôle CSRF de Django exige, en HTTPS, un Referer de la même origine.
        origin = self.host.rstrip("/")
        self.client.headers.update(
            {"X-CSRFToken": self.account["csrf_token"], "Referer": f"{origin}/", "Origin": origin}
        )

    def manage(self, edition: str, path: str) -> str:
        return f"{API}/manage/editions/{self.editions[edition]}/{path}"


class Author(Persona):
    """Auteur pendant le pic de clôture : sauvegarde automatique, PDF, vérification, envoi."""

    persona = "author"
    weight = 15

    def on_start(self) -> None:
        super().on_start()
        self.draft: int | None = None
        self.submitted = False

    def _draft(self) -> int | None:
        if self.draft is None:
            rows = self.client.get(f"{API}/submissions", name="auteur : mes soumissions").json()
            drafts = [row["id"] for row in rows if row["status"] == "draft"]
            self.draft = drafts[0] if drafts else None
            self.submitted = self.draft is None
        return self.draft

    @task(3)
    def mine(self) -> None:
        self.client.get(f"{API}/submissions", name="auteur : mes soumissions")

    @task(5)
    def autosave(self) -> None:
        draft = self._draft()
        if draft is None or self.submitted:
            return
        text = "Résumé enregistré pendant le test de charge. " * random.randint(10, 30)
        self.client.patch(
            f"{API}/submissions/{draft}", json={"abstract": text}, name="auteur : sauvegarde"
        )

    @task(2)
    def detail(self) -> None:
        draft = self._draft()
        if draft is not None:
            self.client.get(f"{API}/submissions/{draft}", name="auteur : soumission")

    @task(1)
    def upload(self) -> None:
        draft = self._draft()
        if draft is None or self.submitted:
            return
        files = {"file": ("article.pdf", tiny_pdf(str(draft)), "application/pdf")}
        self.client.post(
            f"{API}/submissions/{draft}/file", files=files, name="auteur : dépôt du PDF"
        )

    @task(1)
    def check_and_submit(self) -> None:
        draft = self._draft()
        if draft is None or self.submitted:
            return
        check = self.client.get(f"{API}/submissions/{draft}/check", name="auteur : vérification")
        if check.ok and check.json().get("complete"):
            response = self.client.post(f"{API}/submissions/{draft}/submit", name="auteur : envoi")
            self.submitted = response.ok


class Reviewer(Persona):
    """Relecteur : sa liste, une affectation, l'enregistrement d'un brouillon d'évaluation."""

    persona = "reviewer"
    weight = 10

    def _assignments(self) -> list[dict]:
        response = self.client.get(
            self.manage("evaluation", "reviews/assignments"), name="relecteur : affectations"
        )
        return response.json() if response.ok else []

    @task(3)
    def assignments(self) -> None:
        self._assignments()

    @task(3)
    def review(self) -> None:
        """Brouillon d'une évaluation non envoyée (sauvegarde), parfois suivi de l'envoi ;
        une évaluation envoyée ne se modifie qu'en la renvoyant (RG-06)."""
        pending = [
            row
            for row in self._assignments()
            if row.get("can_edit") and row.get("review_status") != "submitted"
        ]
        if not pending:
            return
        assignment = random.choice(pending)["id"]
        base = self.manage("evaluation", f"reviews/assignments/{assignment}")
        detail = self.client.get(base, name="relecteur : affectation")
        if not detail.ok or not detail.json().get("grid"):
            return
        grid = detail.json()["grid"]
        scores = {
            criterion["code"]: random.randint(grid["scale_min"], grid["scale_max"])
            for criterion in grid["criteria"]
        }
        saved = self.client.put(
            f"{base}/review",
            json={
                "scores": scores,
                "recommendation": random.choice(["accept", "accept_minor", "reject"]),
                "confidence": random.randint(1, 5),
                "comment_to_authors": "Brouillon enregistré pendant le test de charge.",
            },
            name="relecteur : brouillon d'évaluation",
        )
        if saved.ok and random.random() < 0.25:
            self.client.post(f"{base}/review/submit", name="relecteur : envoi de l'évaluation")


class Participant(Persona):
    """Participant inscrit : « Mon inscription », devis, tarifs."""

    persona = "participant"
    weight = 10

    @task(4)
    def mine(self) -> None:
        rows = self.client.get(f"{API}/registrations", name="participant : mes inscriptions")
        if rows.ok and rows.json():
            registration = rows.json()[0]["id"]
            self.client.get(f"{API}/registrations/{registration}", name="participant : inscription")

    @task(2)
    def quote(self) -> None:
        self.client.post(
            f"{API}/registrations/quote", json={"category": "chercheur"}, name="participant : devis"
        )


class Newcomer(Persona):
    """Nouvel inscrit : devis, puis commande par virement (pro forma générée : « (PDF) »)."""

    persona = "newcomer"
    weight = 5

    def on_start(self) -> None:
        super().on_start()
        self.ordered = False

    @task
    def register(self) -> None:
        self.client.post(
            f"{API}/registrations/quote", json={"category": "chercheur"}, name="participant : devis"
        )
        if not self.ordered:
            with self.client.post(
                f"{API}/registrations",
                json={"category": "chercheur", "method": "transfer"},
                name=f"participant : commande {PDF_TAG}",
                catch_response=True,
            ) as response:
                # Déjà inscrit (compte partagé entre utilisateurs simulés) : attendu.
                if response.status_code in (201, 409):
                    response.success()
            self.ordered = True
        self.client.get(f"{API}/registrations", name="participant : mes inscriptions")


class Committee(Persona):
    """Comité : listes paginées, classement, avancement, tableaux de bord et rapports."""

    persona = "committee"
    weight = 5
    wait_time = between(2, 6)

    def on_start(self) -> None:
        super().on_start()
        self.scope = self.account.get("scope", "evaluation")
        self.pages: dict[str, int] = {}

    def page_of(self, path: str, name: str) -> None:
        """Une page au hasard d'une liste paginée par 50 (nombre de pages lu la première
        fois, comme l'écran qui affiche la pagination)."""
        url = self.manage(self.scope, path)
        if path not in self.pages:
            response = self.client.get(f"{url}?page_size=50", name=name)
            count = response.json().get("count", 0) if response.ok else 0
            self.pages[path] = max(1, -(-count // 50))
            return
        page = random.randint(1, self.pages[path])
        self.client.get(f"{url}?page={page}&page_size=50", name=name)

    @task
    def browse(self) -> None:
        if self.scope == "evaluation":
            self.page_of("submissions", "comité : soumissions (page)")
            for path, name in (
                ("review-submissions?page_size=50", "comité : évaluations par soumission"),
                ("review-progress", "comité : avancement des évaluations"),
                ("ranking", "comité : classement"),
                ("submissions/stats", "comité : statistiques"),
                ("reports/reviews", "comité : rapport de relecture"),
            ):
                self.client.get(self.manage("evaluation", path), name=name)
        else:
            self.page_of("registrations", "comité : inscriptions (page)")
            for path, name in (
                ("billing/dashboard", "comité : tableau de bord financier"),
                ("billing/payments?page_size=50", "comité : paiements"),
                ("reports/finance", "comité : rapport financier"),
            ):
                self.client.get(self.manage("call", path), name=name)


@events.quitting.add_listener
def verdict(environment, **_kwargs) -> None:
    """p95 et taux d'erreur hors PDF ; code de sortie 1 si l'objectif n'est pas atteint."""
    merged: dict[int, int] = {}
    requests = failures = 0
    for entry in environment.stats.entries.values():
        if PDF_TAG in entry.name:
            continue
        requests += entry.num_requests
        failures += entry.num_failures
        for duration, count in entry.response_times.items():
            merged[duration] = merged.get(duration, 0) + count
    if not requests:
        print("Verdict : aucune requête comptée.")
        environment.process_exit_code = 1
        return
    p95 = calculate_response_time_percentile(merged, sum(merged.values()), 0.95)
    ratio = failures / requests
    ok = p95 < P95_TARGET_MS and ratio < FAILURE_TARGET
    print(
        f"Verdict : {'OBJECTIF ATTEINT' if ok else 'OBJECTIF NON ATTEINT'} : "
        f"p95 {p95} ms (cible < {P95_TARGET_MS}), erreurs {ratio:.2%} "
        f"(cible < {FAILURE_TARGET:.0%}), {requests} requêtes hors PDF."
    )
    environment.process_exit_code = 0 if ok else 1
