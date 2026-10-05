import pytest
from django.db import IntegrityError

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_user_normalizes_email():
    user = User.objects.create_user("  Alice.Kone@Univ-Example.CI ", password="x" * 12)
    assert user.email == "alice.kone@univ-example.ci"


def test_create_user_requires_email():
    with pytest.raises(ValueError, match="obligatoire"):
        User.objects.create_user("", password="x" * 12)


def test_password_is_hashed():
    user = User.objects.create_user("a@example.org", password="motdepasse-solide")
    assert user.password != "motdepasse-solide"
    assert user.check_password("motdepasse-solide")


def test_email_is_unique_regardless_of_case():
    User.objects.create_user("a@example.org", password="x" * 12)
    with pytest.raises(IntegrityError):
        User.objects.create_user("A@EXAMPLE.ORG", password="x" * 12)


def test_default_locale_is_french():
    assert User.objects.create_user("b@example.org").locale == "fr"


def test_user_without_password_cannot_log_in():
    user = User.objects.create_user("c@example.org")
    assert not user.has_usable_password()
