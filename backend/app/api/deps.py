"""Shared dependencies: database session and the current user.

One authentication path for three kinds of caller:

  * a browser, carrying a JWT in the Authorization header;
  * a browser fetching an <img>, which cannot set headers at all and so
    falls back to the session cookie;
  * a CI job, carrying an API token.

Keeping them in one place matters more than it sounds. When token
authentication lived only on the result-reporting routes, a build that
needed to look up a case id got a 401 from an endpoint it had every right
to read.
"""
from datetime import datetime, timedelta, timezone
import hashlib

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..models import ApiToken, User

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# An <img> tag cannot send an Authorization header, so attachment requests
# made by the browser itself would always be rejected. Login therefore also
# drops a session cookie, and that is accepted as a fallback.
SESSION_COOKIE = "tm_session"

# API tokens are prefixed so they can be told apart from a JWT on sight
TOKEN_PREFIX = "tm_"


def create_token(user: User) -> str:
    settings = get_settings()
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_ttl_minutes)
    return jwt.encode({"sub": str(user.id), "exp": expires},
                      settings.secret_key, algorithm="HS256")


def _user_from_api_token(raw: str, session: Session) -> User:
    token = session.scalar(
        select(ApiToken).where(ApiToken.prefix == raw[:12],
                               ApiToken.is_active.is_(True)))
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if token is None or token.token_hash != digest:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "gecersiz token")
    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token suresi dolmus")

    user = session.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token sahibi pasif")

    # a timestamp per request would write on every read; a minute's
    # granularity is enough to answer "is this token still in use?"
    now = datetime.now(timezone.utc)
    if token.last_used_at is None or (now - token.last_used_at).total_seconds() > 60:
        token.last_used_at = now
        session.commit()
    return user


def current_user(request: Request,
                 token: str | None = Depends(oauth2),
                 session: Session = Depends(get_session)) -> User:
    raw = token or request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "kimlik dogrulama gerekli")

    if raw.startswith(TOKEN_PREFIX):
        return _user_from_api_token(raw, session)

    try:
        payload = jwt.decode(raw, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "gecersiz oturum")
    user = session.scalar(select(User).where(User.id == int(payload["sub"])))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "kullanici bulunamadi")
    return user
