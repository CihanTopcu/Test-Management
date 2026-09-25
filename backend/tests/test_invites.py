"""Setting a password through an invitation or reset link.

An administrator used to type everyone's password and pass it on. Now the
person sets it themselves; these pin down the parts that make that safe --
single use, only the newest link works, links expire, and "forgot my
password" does not reveal who has an account.
"""
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select

from app.models import PasswordToken, User


def new_account(app_client, admin, active=True):
    email = f"davet-{secrets.token_hex(3)}@test.local"
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Davetli", "email": email, "is_active": active})
    uid = next(u["id"] for u in app_client.get("/api/admin/users", headers=admin).json()
               if u["email"] == email)
    return uid, email


def token_of(link: str) -> str:
    return parse_qs(urlparse(link.replace("#/", "")).query)["token"][0]


def test_invitation_sets_the_password_and_signs_in(app_client, admin):
    uid, email = new_account(app_client, admin)
    invite = app_client.post(f"/api/admin/users/{uid}/invite", headers=admin).json()
    token = token_of(invite["link"])
    assert invite["emailed"] is False          # no SMTP in the test settings

    info = app_client.get(f"/api/auth/password-token?token={token}").json()
    assert info["email"] == email and info["purpose"] == "invite"

    short = app_client.post("/api/auth/set-password",
                            json={"token": token, "password": "kisa"})
    assert short.status_code == 400

    done = app_client.post("/api/auth/set-password",
                           json={"token": token, "password": "kendi-parolam-123"})
    assert done.status_code == 200, done.text
    me = app_client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {done.json()['access_token']}"}).json()
    assert me["email"] == email

    # single use
    again = app_client.post("/api/auth/set-password",
                            json={"token": token, "password": "baska-parola-456"})
    assert again.status_code == 404

    login = app_client.post("/api/auth/token", data={
        "username": email, "password": "kendi-parolam-123"})
    assert login.status_code == 200


def test_a_new_link_voids_the_previous_one(app_client, admin):
    uid, _ = new_account(app_client, admin)
    first = token_of(app_client.post(f"/api/admin/users/{uid}/invite",
                                     headers=admin).json()["link"])
    second = token_of(app_client.post(f"/api/admin/users/{uid}/invite",
                                      headers=admin).json()["link"])
    assert app_client.get(f"/api/auth/password-token?token={first}").status_code == 404
    assert app_client.get(f"/api/auth/password-token?token={second}").status_code == 200


def test_links_expire(app_client, admin, db):
    uid, _ = new_account(app_client, admin)
    token = token_of(app_client.post(f"/api/admin/users/{uid}/invite",
                                     headers=admin).json()["link"])
    row = db.scalar(select(PasswordToken).where(
        PasswordToken.user_id == uid, PasswordToken.used_at.is_(None))
        .order_by(PasswordToken.id.desc()))
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    assert app_client.get(f"/api/auth/password-token?token={token}").status_code == 404


def test_only_the_hash_is_stored(app_client, admin, db):
    uid, _ = new_account(app_client, admin)
    token = token_of(app_client.post(f"/api/admin/users/{uid}/invite",
                                     headers=admin).json()["link"])
    stored = db.scalars(select(PasswordToken.token_hash)
                        .where(PasswordToken.user_id == uid)).all()
    assert token not in stored


def test_forgot_answers_the_same_for_anyone(app_client, admin, db):
    uid, email = new_account(app_client, admin)
    unknown = app_client.post("/api/auth/forgot", json={"email": "yok@test.local"})
    known = app_client.post("/api/auth/forgot", json={"email": email})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()
    # but only the real account got a reset link
    assert db.scalar(select(PasswordToken).where(
        PasswordToken.user_id == uid, PasswordToken.purpose == "reset")) is not None


def test_inactive_accounts_get_no_link(app_client, admin):
    uid, _ = new_account(app_client, admin, active=False)
    assert app_client.post(f"/api/admin/users/{uid}/invite",
                           headers=admin).status_code == 400


def test_only_admins_invite(app_client, admin):
    uid, email = new_account(app_client, admin)
    token = token_of(app_client.post(f"/api/admin/users/{uid}/invite",
                                     headers=admin).json()["link"])
    signed_in = app_client.post("/api/auth/set-password", json={
        "token": token, "password": "kendi-parolam-123"}).json()
    headers = {"Authorization": f"Bearer {signed_in['access_token']}"}
    assert app_client.post(f"/api/admin/users/{uid}/invite",
                           headers=headers).status_code == 403
