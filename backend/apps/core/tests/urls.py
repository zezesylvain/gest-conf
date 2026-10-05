"""Vues factices servant uniquement à tester le format d'erreur normalisé."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.urls import path
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


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
    def get(self, request):
        return Response()


class Http404View(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise Http404


class DjangoPermissionDeniedView(APIView):
    permission_classes = (AllowAny,)

    def get(self, request):
        raise DjangoPermissionDenied


urlpatterns = [
    path("field-validation", FieldValidationView.as_view()),
    path("non-field-validation", NonFieldValidationView.as_view()),
    path("protected", ProtectedView.as_view()),
    path("http404", Http404View.as_view()),
    path("django-permission-denied", DjangoPermissionDeniedView.as_view()),
]
