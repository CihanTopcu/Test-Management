"""Signing in with the company account, against a fake identity provider.

The provider is played by an RSA key made here: the tests sign ID tokens
with it, and one made by another key must be refused. Nothing talks to
Microsoft.
"""
import secrets
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://login.ornek.test/tenant/v2.0"
CLIENT = "dgtest-client"


@pytest.fixture
def idp(monkeypatch):
    from app import oidc
    from app.config import get_settings

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", ISSUER)
    monkeypatch.setattr(s, "oidc_client_id", CLIENT)
    monkeypatch.setattr(s, "oidc_client_secret", "gizli")
    monkeypatch.setattr(oidc, "discovery", lambda: {
        "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/keys"})
    monkeypatch.setattr(oidc, "_signing_key", lambda token: key.public_key())

    class Provider:
        """Issues the ID token the next exchange returns."""
        claims: dict = {}
        signer = key

        def token(self, **override):
            now = int(time.time())
            body = {"iss": ISSUER, "aud": CLIENT, "iat": now, "exp": now + 300,
                    **self.claims, **override}
            return jwt.encode(body, self.signer, algorithm="RS256")

    provider = Provider()
    monkeypatch.setattr(oidc, "_exchange", lambda code, verifier: {"id_token": provider.token()})
    return provider


def browser(app_client):
    """A client of its own: no cookies from the rest of the suite, and
    redirects left for the test to read."""
    from starlette.testclient import TestClient
    return TestClient(app_client.app, follow_redirects=False)


def begin(client):
    r = client.get("/api/auth/oidc/login")
    assert r.status_code == 302, r.text
    query = parse_qs(urlparse(r.headers["location"]).query)
    return query


def test_company_account_signs_in(app_client, admin, idp):
    client = browser(app_client)
    assert client.get("/api/auth/methods").json() == {"sso": True, "sso_label": "Microsoft"}

    query = begin(client)
    assert query["code_challenge_method"] == ["S256"] and query["client_id"] == [CLIENT]
    idp.claims = {"nonce": query["nonce"][0], "preferred_username": "ADMIN@test.local"}

    back = client.get(f"/api/auth/oidc/callback?code=abc&state={query['state'][0]}")
    assert back.status_code == 302
    assert back.headers["location"].endswith("/#/sso")      # no token in the address

    token = client.post("/api/auth/session-token").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "admin@test.local"


def outcome(client, state, **claims):
    r = client.get(f"/api/auth/oidc/callback?code=abc&state={state}")
    assert r.status_code == 302
    location = r.headers["location"]
    return parse_qs(urlparse(location.replace("#/", "")).query).get("error", [None])[0]


def test_a_forged_state_is_refused(app_client, admin, idp):
    client = browser(app_client)
    query = begin(client)
    idp.claims = {"nonce": query["nonce"][0], "email": "admin@test.local"}
    assert outcome(client, "baska-bir-state") == "state"


def test_a_token_signed_by_someone_else_is_refused(app_client, admin, idp):
    client = browser(app_client)
    query = begin(client)
    idp.claims = {"nonce": query["nonce"][0], "email": "admin@test.local"}
    idp.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert outcome(client, query["state"][0]) == "token"


def test_a_replayed_token_with_another_nonce_is_refused(app_client, admin, idp):
    client = browser(app_client)
    query = begin(client)
    idp.claims = {"nonce": "eski-bir-nonce", "email": "admin@test.local"}
    assert outcome(client, query["state"][0]) == "token"


def test_only_people_who_already_have_an_account_get_in(app_client, admin, idp):
    client = browser(app_client)
    query = begin(client)
    idp.claims = {"nonce": query["nonce"][0], "email": f"yabanci-{secrets.token_hex(3)}@dgpays.com"}
    assert outcome(client, query["state"][0]) == "unknown"


def test_an_inactive_account_does_not_get_in(app_client, admin, idp):
    email = f"eski-{secrets.token_hex(3)}@test.local"
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Ayrılan", "email": email, "is_active": False})
    client = browser(app_client)
    query = begin(client)
    idp.claims = {"nonce": query["nonce"][0], "email": email}
    assert outcome(client, query["state"][0]) == "unknown"


def test_nothing_changes_when_sso_is_not_configured(app_client):
    client = browser(app_client)
    assert client.get("/api/auth/methods").json()["sso"] is False
    assert client.get("/api/auth/oidc/login").status_code == 404
