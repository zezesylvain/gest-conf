"""Vues factices servant uniquement aux tests du socle (erreurs, CSRF, débit, pagination)."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, HttpRequest, JsonResponse
from django.middleware.csrf import get_token
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.errors import ErrorCode, Invalid, NotAllowed, QuotaExceeded, RuleViolation
from apps.core.permissions import CsrfEnforced

THROTTLE_TEST_SCOPE = "core_tests"


class _TitleSerializer(serializers.Serializer):
    title = serializers.CharField()


class FieldValidationView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        _TitleSerializer(data=request.data).is_valid(raise_exception=True)
        return Response()


class NonFieldValidationView(APIView):
    permission_classes = (AllowAny,)

    def post(self, request):
        raise ValidationError("Erreur globale")


class ProtectedView(APIView):
    """Permission par défaut (IsAuthenticated), authentification par défaut (session)."""

    def get(self, request):
        return Response({"user": request.user.email})

    def post(self, request):
        return Response({"user": request.user.email})


class Http404View(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise Http404


class DjangoPermissionDeniedView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise DjangoPermissionDenied


class EchoView(APIView):
    """Lit le corps de la requête : erreurs de parseur et de type de contenu."""

    permission_classes = (AllowAny,)

    def post(self, request):
        return Response({"received": request.data})


DOMAIN_ERRORS = {
    "rule": lambda: RuleViolation(
        "Cet objet est utilisé ailleurs.",
        code=ErrorCode.IN_USE,
        fields={"track": ["Déjà utilisé."]},
    ),
    "not-allowed": lambda: NotAllowed(),
    "invalid": lambda: Invalid(fields={"end": ["Doit suivre le début."]}),
    "quota": lambda: QuotaExceeded(retry_after=42.3),
}


class DomainErrorView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request, kind):
        raise DOMAIN_ERRORS[kind]()


class CsrfEnforcedView(APIView):
    """POST public protégé par CsrfEnforced (plan L1 §4.6, cas 3)."""

    permission_classes = (CsrfEnforced,)

    def post(self, request):
        return Response({"ok": True})


class ScopedThrottleView(APIView):
    """Vue publique limitée par la portée de test (taux posé par le test)."""

    permission_classes = (AllowAny,)
    throttle_scope = THROTTLE_TEST_SCOPE

    def get(self, request):
        return Response({"ok": True})


class PaginatedView(GenericAPIView):
    """Liste de 230 entiers paginée par la classe par défaut (StandardPagination)."""

    permission_classes = (AllowAny,)

    def get(self, request):
        page = self.paginate_queryset(list(range(230)))
        return self.get_paginated_response(page)


def csrf_token_view(request: HttpRequest) -> JsonResponse:
    """Vue Django ordinaire qui pose le cookie CSRF (comme GET auth/session d'allauth)."""
    return JsonResponse({"token": get_token(request)})


def csrf_protected_django_view(request: HttpRequest) -> JsonResponse:
    """Vue Django ordinaire, protégée par le middleware CSRF (plan L1 §4.6, cas 1)."""
    return JsonResponse({"ok": True})


urlpatterns = [
    path("field-validation", FieldValidationView.as_view()),
    path("non-field-validation", NonFieldValidationView.as_view()),
    path("protected", ProtectedView.as_view()),
    path("http404", Http404View.as_view()),
    path("django-permission-denied", DjangoPermissionDeniedView.as_view()),
    path("echo", EchoView.as_view()),
    path("domain-error/<str:kind>", DomainErrorView.as_view()),
    path("csrf-enforced", CsrfEnforcedView.as_view()),
    # Segment libre : chemin décodé contenant des caractères de contrôle (journalisation).
    path("csrf-enforced-path/<str:anything>", CsrfEnforcedView.as_view()),
    path("csrf-token", csrf_token_view),
    path("csrf-django-view", csrf_protected_django_view),
    path("throttled", ScopedThrottleView.as_view()),
    path("paginated", PaginatedView.as_view()),
]
