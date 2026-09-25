"""Sign-in.

Passwords did not come across from TestRail -- its API never exposes them --
so imported accounts start without one and have to be given a password (or
wired to SSO) before first use.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ... import oidc
from ...db import get_session
from ...notifications import send_now
from ...security import hash_password, verify_password
from ...models import PasswordToken, User
from ...config import get_settings
from ..deps import SESSION_COOKIE, create_token, current_user
from ..schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("auth")

# an invitation waits for someone back from leave; a reset should not
LIFETIME = {"invite": timedelta(days=7), "reset": timedelta(hours=1)}
MIN_PASSWORD = 10


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(session: Session, user: User, purpose: str,
                created_by: User | None = None) -> str:
    """A fresh single-use link token; earlier unused ones for the same
    person and purpose stop working, so only the latest link is live.
    The caller commits."""
    now = datetime.now(timezone.utc)
    session.execute(
        update(PasswordToken)
        .where(PasswordToken.user_id == user.id,
               PasswordToken.purpose == purpose,
               PasswordToken.used_at.is_(None))
        .values(expires_at=now))
    raw = secrets.token_urlsafe(32)
    session.add(PasswordToken(
        user_id=user.id, token_hash=_hash(raw), purpose=purpose,
        created_on=now, expires_at=now + LIFETIME[purpose],
        created_by=created_by.id if created_by else None))
    return raw


def link_for(raw: str) -> str:
    return f"{get_settings().public_url}/#/set-password?token={raw}"


def _live(session: Session, raw: str) -> PasswordToken:
    row = session.scalar(select(PasswordToken).where(PasswordToken.token_hash == _hash(raw)))
    now = datetime.now(timezone.utc)
    if row is None or row.used_at is not None:
        raise HTTPException(404, "baglanti gecersiz ya da kullanilmis")
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(404, "baglantinin suresi dolmus")
    return row


def _sign_in(response: Response, user: User) -> dict:
    token = create_token(user)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", path="/api",
        max_age=get_settings().access_token_ttl_minutes * 60,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/token")
def login(response: Response,
          form: OAuth2PasswordRequestForm = Depends(),
          session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == form.username))
    if user is None or not user.is_active or not user.password_hash:
        raise HTTPException(401, "kullanici adi veya parola hatali")
    if not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "kullanici adi veya parola hatali")
    user.last_login_at = datetime.now(timezone.utc)
    session.commit()
    return _sign_in(response, user)


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/api")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


class ForgotIn(BaseModel):
    email: str


@router.post("/forgot", status_code=202)
def forgot_password(payload: ForgotIn, session: Session = Depends(get_session)):
    """Send a reset link, if the address belongs to an active account.

    The answer is the same either way, so this cannot be used to find out
    who has an account. With no mail server there is nobody to send it to;
    the sign-in page then tells people to ask an administrator.
    """
    user = session.scalar(select(User).where(User.email == payload.email.strip()))
    if user is not None and user.is_active:
        raw = issue_token(session, user, "reset")
        session.commit()
        sent, reason = send_now(
            user.email, "DGTest parola sıfırlama",
            "\n\n".join([
                f"Merhaba {user.name},",
                "DGTest parolanızı sıfırlamak için bu bağlantıyı bir saat içinde açın:",
                link_for(raw),
                "Bu isteği siz yapmadıysanız bu e-postayı yok sayabilirsiniz; "
                "parolanız değişmez.",
            ]))
        if not sent:
            log.warning("parola sifirlama e-postasi gonderilemedi (%s): %s", user.email, reason)
    return {"mail": bool(get_settings().smtp_host)}


@router.get("/password-token")
def password_token(token: str, session: Session = Depends(get_session)):
    """What the set-password page needs to greet the person by name."""
    row = _live(session, token)
    user = session.get(User, row.user_id)
    return {"purpose": row.purpose, "email": user.email, "name": user.name,
            "min_length": MIN_PASSWORD}


class SetPasswordIn(BaseModel):
    token: str
    password: str


@router.post("/set-password")
def set_password(payload: SetPasswordIn, response: Response,
                 session: Session = Depends(get_session)):
    """Use an invitation or reset link. It signs the person in, because
    making them type the password they just chose twice is pure friction."""
    row = _live(session, payload.token)
    if len(payload.password) < MIN_PASSWORD:
        raise HTTPException(400, f"parola en az {MIN_PASSWORD} karakter olmali")
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(404, "baglanti gecersiz ya da kullanilmis")
    now = datetime.now(timezone.utc)
    user.password_hash = hash_password(payload.password)
    user.last_login_at = now
    row.used_at = now
    # every other open link for this person dies with this one
    session.execute(
        update(PasswordToken)
        .where(PasswordToken.user_id == user.id, PasswordToken.used_at.is_(None))
        .values(expires_at=now))
    session.commit()
    return _sign_in(response, user)


# --- single sign-on -----------------------------------------------------------

@router.get("/methods")
def sign_in_methods():
    """What the sign-in page should offer. Public: it is asked before
    anyone has signed in."""
    return {"sso": oidc.enabled(),
            "sso_label": get_settings().oidc_label if oidc.enabled() else None}


def _back_to_app(error: str | None = None) -> RedirectResponse:
    target = f"{get_settings().public_url.rstrip('/')}/#/sso"
    return RedirectResponse(target + (f"?error={error}" if error else ""), status_code=302)


@router.get("/oidc/login")
def sso_login():
    if not oidc.enabled():
        raise HTTPException(404, "tek oturum acma yapilandirilmamis")
    url, flow = oidc.start()
    response = RedirectResponse(url, status_code=302)
    response.set_cookie(
        oidc.FLOW_COOKIE, flow, httponly=True, samesite="lax",
        path="/api/auth/oidc", max_age=int(oidc.FLOW_TTL.total_seconds()),
        secure=get_settings().public_url.startswith("https://"))
    return response


@router.get("/oidc/callback")
def sso_callback(request: Request, code: str | None = None,
                 state: str | None = None, error: str | None = None,
                 session: Session = Depends(get_session)):
    """Where the provider sends the browser back. Every failure lands on the
    sign-in page with a reason, never on a JSON error page."""
    if error:
        return _back_to_app("denied")
    try:
        email = oidc.finish(code, state, request.cookies.get(oidc.FLOW_COOKIE))
    except oidc.SSOError as exc:
        log.warning("tek oturum acma reddedildi: %s (%s)", exc.code, exc)
        return _back_to_app(exc.code)
    except Exception:                         # provider unreachable, and the like
        log.exception("tek oturum acma basarisiz")
        return _back_to_app("provider")

    user = session.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active:
        log.warning("tek oturum acma: DGTest'te karsiligi olmayan hesap %s", email)
        return _back_to_app("unknown")
    user.last_login_at = datetime.now(timezone.utc)
    session.commit()

    response = _back_to_app()
    response.delete_cookie(oidc.FLOW_COOKIE, path="/api/auth/oidc")
    response.set_cookie(
        SESSION_COOKIE, create_token(user), httponly=True, samesite="lax",
        path="/api", max_age=get_settings().access_token_ttl_minutes * 60,
        secure=get_settings().public_url.startswith("https://"))
    return response


@router.post("/session-token")
def session_token(user: User = Depends(current_user)):
    """The bearer token for a browser that holds only the session cookie --
    how a single sign-on hands over without a token in the address bar."""
    return {"access_token": create_token(user), "token_type": "bearer"}
