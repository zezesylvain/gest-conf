"""Données du parcours auteur de bout en bout (plan L3, F14), créées par les services comme
un opérateur le ferait : conférence, édition publiée et courante, appel ouvert, thématique,
type à PDF obligatoire ; PDF de test porteur de métadonnées (retirées en double aveugle).

Lu sur l'entrée standard de ``manage.py shell`` par ``e2e/django.ts`` ; imprime du JSON.
"""

import datetime as dt
import json
import tempfile
from zoneinfo import ZoneInfo

from django.utils import timezone
from pypdf import PdfWriter

from apps.conferences import services as conferences
from apps.core.actor import Actor

actor = Actor.command("cli:e2e")
zone = "Africa/Abidjan"
conference = conferences.create_conference(
    slug="gestconf-e2e", name_fr="Colloque E2E", name_en="E2E Conference", actor=actor
)
edition = conferences.create_edition(
    conference=conference,
    actor=actor,
    code="E2E27",
    slug="e2e27",
    year=2027,
    title_fr="Colloque E2E 2027",
    title_en="E2E Conference 2027",
    timezone=zone,
    start_date=dt.date(2027, 3, 1),
    end_date=dt.date(2027, 3, 3),
)
conferences.create_track(
    edition,
    {"code": "ia", "name_fr": "Intelligence artificielle", "name_en": "AI"},
    actor=actor,
)
conferences.create_submission_type(
    edition,
    {
        "code": "oral",
        "label_fr": "Communication orale",
        "label_en": "Oral paper",
        "file_policy": "required",
        "max_file_mb": 5,
    },
    actor=actor,
)
now = timezone.localtime(timezone.now(), ZoneInfo(zone)).replace(tzinfo=None, microsecond=0)
conferences.create_key_date(
    edition, {"code": "call_open", "at_local": now - dt.timedelta(days=1)}, actor=actor
)
conferences.create_key_date(
    edition,
    {"code": "call_close", "at_local": now + dt.timedelta(days=10)},
    actor=actor,
)
conferences.set_edition_status(edition, "published", actor=actor, reason="E2E")
conferences.set_current_edition(conference, edition, actor=actor)

writer = PdfWriter()
writer.add_blank_page(595, 842)
writer.add_metadata({"/Author": "Awa Koné", "/Title": "Article de test"})
with tempfile.NamedTemporaryFile(prefix="gestconf-e2e-", suffix=".pdf", delete=False) as handle:
    writer.write(handle)

print(json.dumps({"code": edition.code, "pdf": handle.name}))
