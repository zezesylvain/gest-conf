"""Fabriques de l'application conferences."""

import datetime as dt

import factory
from factory.django import DjangoModelFactory


class ConferenceFactory(DjangoModelFactory):
    class Meta:
        model = "conferences.Conference"
        django_get_or_create = ("slug",)

    slug = "gestconf"
    name_fr = "Conférence scientifique"
    name_en = "Scientific conference"


class EditionFactory(DjangoModelFactory):
    class Meta:
        model = "conferences.Edition"

    conference = factory.SubFactory(ConferenceFactory)
    code = factory.Sequence(lambda n: f"GC{26 + n}")
    slug = factory.Sequence(lambda n: f"edition-{26 + n}")
    year = factory.Sequence(lambda n: 2026 + n % 50)
    title_fr = factory.Sequence(lambda n: f"Édition {26 + n}")
    title_en = factory.Sequence(lambda n: f"Edition {26 + n}")
    start_date = dt.date(2027, 6, 1)
    end_date = dt.date(2027, 6, 3)
    timezone = "Africa/Abidjan"


class TrackFactory(DjangoModelFactory):
    class Meta:
        model = "conferences.Track"

    edition = factory.SubFactory(EditionFactory)
    code = factory.Sequence(lambda n: f"track-{n}")
    name_fr = factory.Sequence(lambda n: f"Thématique {n}")
    name_en = factory.Sequence(lambda n: f"Track {n}")


class SubmissionTypeFactory(DjangoModelFactory):
    class Meta:
        model = "conferences.SubmissionType"

    edition = factory.SubFactory(EditionFactory)
    code = factory.Sequence(lambda n: f"type-{n}")
    label_fr = "Communication orale"
    label_en = "Oral presentation"
    default_duration_min = 20


class KeyDateFactory(DjangoModelFactory):
    class Meta:
        model = "conferences.KeyDate"

    edition = factory.SubFactory(EditionFactory)
    code = "call_open"
    at = dt.datetime(2027, 1, 10, 0, 0, tzinfo=dt.UTC)
