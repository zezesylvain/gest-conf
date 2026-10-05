"""Gabarits d'e-mails propres aux tests (tests/templates/tests/email)."""

from apps.communications.services import register_email_template

PLAIN = "tests/email/plain"
SENSITIVE = "tests/email/sensitive"
FAST = "tests/email/fast"

register_email_template(PLAIN)
register_email_template(SENSITIVE, sensitive=True)
register_email_template(FAST, sensitive=True, fast_path=True)
