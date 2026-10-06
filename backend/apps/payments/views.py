"""Routes des paiements et de la facturation (plan L6 §4).

Gestion : lecture ``finance.read``, mentions de facturation ``pricing.write`` avec
réauthentification récente (J1).
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.payments.serializers import BillingProfileSerializer
from apps.payments.services import billing


class BillingProfileViewSet(ManageViewSet):
    """``…/billing/profile`` : mentions de facturation de l'édition (Q8)."""

    serializer_class = BillingProfileSerializer
    required_capabilities = {"retrieve": C.FINANCE_READ, "partial_update": C.PRICING_WRITE}

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "partial_update":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(operation_id="manage_billing_profile_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(BillingProfileSerializer(billing.billing_profile(self.edition)).data)

    @extend_schema(operation_id="manage_billing_profile_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        current = billing.billing_profile(self.edition)
        serializer = BillingProfileSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = billing.update_billing_profile(
            self.edition, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(BillingProfileSerializer(profile).data)
