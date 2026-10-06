"""Jeton QR d'une inscription (plan L6, J11 ; plan L7, K2) : titre d'accès à l'accueil.

Jamais dans une URL, ni dans un journal, ni dans la liste hors ligne (empreinte SHA-256
seulement, K5). L'empreinte se calcule sur le texte du QR encodé en UTF-8, comme le fait
l'écran d'accueil (Web Crypto).
"""

from __future__ import annotations

import hashlib
import secrets


def new_token() -> str:
    """192 bits aléatoires, en base64 URL (32 caractères)."""
    return secrets.token_urlsafe(24)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
