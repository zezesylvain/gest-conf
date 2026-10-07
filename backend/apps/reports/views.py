"""Routes des rapports et du fil d'activité (plan L8, N13 et N14), gestion (2FA).

- ``…/reports`` : sections ouvertes au compte ; ``…/reports/{section}`` : ses tableaux ;
  ``…/reports/{section}/export?file_format=csv|xlsx|pdf`` : export **journalisé**. Chaque
  section est vérifiée côté serveur contre la capacité qui protège déjà ses données
  (règle n° 2) ; aucune donnée nominative.
- ``…/activity`` (``tasks.read``) : les 50 dernières entrées du journal, restreintes à une
  **liste blanche** d'actions non sensibles, sans les valeurs avant et après.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text, xlsx_response, xlsx_workbook
from apps.reports import activity, services
from apps.reports.pdf import tables_pdf
from apps.reports.serializers import (
    ActivityEntrySerializer,
    ReportSectionSerializer,
    SectionSummarySerializer,
    tables_data,
)

FORMATS = ("csv", "xlsx", "pdf")
FORMAT_ENUM = list(FORMATS)


class ReportViewSet(ManageViewSet):
    """La lecture de l'édition ouvre l'écran ; chaque section exige en plus sa capacité."""

    pagination_class = None
    filter_backends = ()
    serializer_class = ReportSectionSerializer
    required_capabilities = {
        "list": C.EDITION_READ,
        "retrieve": C.EDITION_READ,
        "export": C.EDITION_READ,
    }

    def section(self, code: str) -> services.Section:
        section = services.BY_CODE.get(code)
        if section is None:
            raise Http404
        if not self.access.has(section.capability):
            raise PermissionDenied(_("Section réservée."))
        return section

    @extend_schema(
        operation_id="manage_reports_list", responses={200: SectionSummarySerializer(many=True)}
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = [
            {"code": section.code, "label": str(section.label)}
            for section in services.available(self.access.capabilities)
        ]
        return Response(SectionSummarySerializer(rows, many=True).data)

    @extend_schema(operation_id="manage_reports_retrieve", responses={200: ReportSectionSerializer})
    def retrieve(self, request: Request, edition_id: int, section: str) -> Response:
        current = self.section(section)
        tables = services.compute(current, self.edition)
        return Response(
            ReportSectionSerializer(
                {"code": current.code, "label": str(current.label), "tables": tables_data(tables)}
            ).data
        )

    @extend_schema(
        operation_id="manage_reports_export",
        parameters=[OpenApiParameter("file_format", str, enum=FORMAT_ENUM)],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int, section: str) -> HttpResponse:
        file_format = request.query_params.get("file_format", "csv")
        if file_format not in FORMATS:
            raise Invalid(fields={"file_format": [_("csv, xlsx ou pdf attendu.")]})
        current = self.section(section)
        tables = services.compute(current, self.edition)
        record(
            "report.exported",
            actor=Actor.from_request(request),
            edition=self.edition,
            after={"section": current.code, "format": file_format},
        )
        now = timezone.now()
        name = f"rapport-{current.code}-{self.edition.code}-{now:%Y%m%d}.{file_format}"
        return render_tables(file_format, str(current.label), self.edition, tables, name, now)


def render_tables(file_format, label, edition, tables, name, now) -> HttpResponse:
    """CSV (tableaux à la suite, chacun précédé de son titre), XLSX (une feuille par
    tableau) ou PDF de synthèse ; protégés contre l'injection de formules (L8.0)."""
    if file_format == "xlsx":
        sheets = [(table.title, table.columns, table.rows) for table in tables]
        return xlsx_response(xlsx_workbook(sheets), name)
    if file_format == "pdf":
        title = f"{label} — {edition.title_fr}"
        subtitle = gettext("Produit le %(date)s (UTC)") % {"date": f"{now:%d/%m/%Y %H:%M}"}
        response = HttpResponse(
            tables_pdf(title, subtitle, tables, produced_at=now), content_type="application/pdf"
        )
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
    rows: list[list] = []
    for index, table in enumerate(tables):
        if index:
            rows.append([])
        rows.append([table.title])
        rows.append(list(table.columns))
        rows.extend(table.rows)
    header, *body = rows or [[label]]
    return csv_response(csv_text(header, body), name)


class ActivityViewSet(ManageViewSet):
    """``…/activity`` : fil d'activité du CO (N14)."""

    pagination_class = None
    filter_backends = ()
    serializer_class = ActivityEntrySerializer
    required_capabilities = {"list": C.TASKS_READ}

    @extend_schema(
        operation_id="manage_activity", responses={200: ActivityEntrySerializer(many=True)}
    )
    def list(self, request: Request, edition_id: int) -> Response:
        return Response(ActivityEntrySerializer(activity.feed(self.edition), many=True).data)
