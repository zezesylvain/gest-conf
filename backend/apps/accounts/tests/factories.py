"""Fabriques de données de test (factory_boy) de l'application accounts."""

import factory
from factory.django import DjangoModelFactory, Password

# Mot de passe de tous les comptes de test (hachage rapide en configuration de test).
DEFAULT_PASSWORD = "motdepasse-de-test-solide"


class UserFactory(DjangoModelFactory):
    class Meta:
        model = "accounts.User"

    email = factory.Sequence(lambda n: f"utilisateur{n}@example.org")
    password = Password(DEFAULT_PASSWORD)
    locale = "fr"
