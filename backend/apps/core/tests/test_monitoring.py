"""Supervision du stockage : sauvegarde en retard, espace disque (plan L9, S4)."""

from __future__ import annotations

import pytest

from apps.core.models import CronHeartbeat

pytestmark = pytest.mark.django_db


def test_s4_check_integrity_flags_a_missing_or_late_backup(settings):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.integrity import check_backup_age

    settings.GESTCONF_STORAGE_MONITORING = True
    settings.GESTCONF_BACKUP_MAX_AGE_HOURS = 26
    assert "Aucune sauvegarde" in check_backup_age()[0]
    beat = CronHeartbeat.objects.create(
        name="backup_db", last_success_at=timezone.now() - timedelta(hours=30)
    )
    assert "il y a 30 h" in check_backup_age()[0]
    beat.last_success_at = timezone.now()
    beat.save()
    assert check_backup_age() == []
    settings.GESTCONF_STORAGE_MONITORING = False
    beat.delete()
    assert check_backup_age() == []


def test_s4_check_integrity_flags_low_disk_space(settings, tmp_path, monkeypatch):
    import shutil as shell_utils
    from collections import namedtuple

    from apps.core import integrity

    settings.GESTCONF_STORAGE_MONITORING = True
    settings.GESTCONF_FILES_DIR = tmp_path / "absent" / "files"
    settings.GESTCONF_BACKUP_DIR = tmp_path
    settings.GESTCONF_DISK_FREE_MIN_MB = 1024
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shell_utils, "disk_usage", lambda path: usage(0, 0, 200 * 1024 * 1024))
    problems = integrity.check_disk_space()
    assert len(problems) == 2 and "200 Mio" in problems[0]
    monkeypatch.setattr(shell_utils, "disk_usage", lambda path: usage(0, 0, 5 * 1024**3))
    assert integrity.check_disk_space() == []
