"""Sign-in.

Passwords did not come across from TestRail -- its API never exposes them --
so imported accounts start without one and have to be given a password (or
wired to SSO) before first use.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_session
from ...security import verify_password
from ...models import User
from ...config import get_settings
from ..deps import SESSION_COOKIE, create_token, current_user
from ..schemas import UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/token")
def login(response: Response,
          form: OAuth2PasswordRequestForm = Depends(),
          session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == form.username))
    if user is None or not user.is_active or not user.password_hash:
        raise HTTPException(401, "kullanici adi veya parola hatali")
    if not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "kullanici adi veya parola hatali")
    token = create_token(user)
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", path="/api",
        max_age=get_settings().access_token_ttl_minutes * 60,
    )
    return {"access_token": token, "token_type": "bearer"}


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/api")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
