"""Password hashing.

bcrypt directly, not through passlib: passlib 1.7.4 reads
``bcrypt.__about__`` during backend detection, which bcrypt 4+ removed, and
the resulting failure surfaces as a confusing "password cannot be longer than
72 bytes" error.

That 72-byte ceiling is real, though, and silently truncating to fit would
mean two different long passwords hashing the same. Pre-hashing with SHA-256
and base64-encoding gives a fixed 44-byte input, so the whole password always
counts.
"""
import base64
import hashlib

import bcrypt


def _prepare(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("ascii"))
    except ValueError:
        return False
