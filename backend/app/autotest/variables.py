"""{{NAME}} placeholders in scenario steps, and the values behind them.

A secret is encrypted with a key derived from SECRET_KEY: a copy of the
database alone does not give away the test passwords in it. Rotating
SECRET_KEY makes the stored secrets unreadable; they then have to be
entered again, which the page says when it happens.
"""
import base64
import hashlib
import re

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
MASK = "••••"


def _fernet() -> Fernet:
    digest = hashlib.sha256(("autotest:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unseal(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def referenced(source: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER.finditer(source)}


def load(session: Session, project_id: int) -> tuple[dict[str, str], set[str], set[str]]:
    """Values by name, the secret values (for masking), and the names whose
    secret could not be decrypted."""
    from ..models import AutoVariable
    values, secrets, broken = {}, set(), set()
    for v in session.scalars(select(AutoVariable).where(AutoVariable.project_id == project_id)):
        if v.is_secret:
            plain = unseal(v.value)
            if plain is None:
                broken.add(v.name)
                continue
            values[v.name] = plain
            if plain:
                secrets.add(plain)
        else:
            values[v.name] = v.value
    return values, secrets, broken


def fill(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def mask(text: str | None, secrets: set[str]) -> str | None:
    if not text:
        return text
    # longest first, so a secret containing another is hidden whole
    for s in sorted(secrets, key=len, reverse=True):
        text = text.replace(s, MASK)
    return text
