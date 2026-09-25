"""Signing in with the company account (OpenID Connect).

DGPays runs on Microsoft 365, so everyone already has an Entra ID account;
a separate DGTest password is one more thing to set, forget and reset, and
it outlives the person's employment. With OIDC_ISSUER, OIDC_CLIENT_ID and
OIDC_CLIENT_SECRET set, the sign-in page offers the company account too.
Nothing here is Microsoft-specific: any OpenID Connect provider works.

What it holds to:

  An account is matched by e-mail to a user who already exists here and is
  active. Nobody is created on the fly -- being in the company directory
  is not the same as being allowed into the test system.

  The authorisation-code flow with PKCE, a state value against forged
  callbacks and a nonce against replayed ID tokens. The three travel in a
  short-lived signed cookie, so the server keeps no session table.

  The ID token is verified -- signature against the provider's published
  keys, issuer, audience, expiry, nonce -- before anything in it is read.
"""
import base64
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt

from .config import get_settings

FLOW_COOKIE = "tm_oidc"
FLOW_TTL = timedelta(minutes=10)
DISCOVERY_TTL = 3600

_discovery: tuple[float, dict] | None = None
_jwks: dict[str, jwt.PyJWKClient] = {}


class SSOError(Exception):
    """Something the sign-in page can name: code is shown as ?error=code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def enabled() -> bool:
    s = get_settings()
    return bool(s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret)


def redirect_uri() -> str:
    return f"{get_settings().public_url.rstrip('/')}/api/auth/oidc/callback"


def discovery() -> dict:
    """The provider's endpoints, from its well-known document, cached."""
    global _discovery
    if _discovery and time.time() - _discovery[0] < DISCOVERY_TTL:
        return _discovery[1]
    issuer = get_settings().oidc_issuer.rstrip("/")
    r = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=15)
    r.raise_for_status()
    _discovery = (time.time(), r.json())
    return _discovery[1]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def start() -> tuple[str, str]:
    """(URL to send the browser to, signed value for the flow cookie)."""
    s = get_settings()
    state, nonce, verifier = (secrets.token_urlsafe(24), secrets.token_urlsafe(24),
                              secrets.token_urlsafe(48))
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    flow = jwt.encode({"state": state, "nonce": nonce, "verifier": verifier,
                       "exp": datetime.now(timezone.utc) + FLOW_TTL},
                      s.secret_key, algorithm="HS256")
    url = discovery()["authorization_endpoint"] + "?" + urlencode({
        "client_id": s.oidc_client_id, "response_type": "code",
        "redirect_uri": redirect_uri(), "response_mode": "query",
        "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256",
        # a shared office machine should not sign in whoever used it last
        "prompt": "select_account",
    })
    return url, flow


def _exchange(code: str, verifier: str) -> dict:
    s = get_settings()
    r = httpx.post(discovery()["token_endpoint"], timeout=15, data={
        "grant_type": "authorization_code", "code": code,
        "redirect_uri": redirect_uri(), "client_id": s.oidc_client_id,
        "client_secret": s.oidc_client_secret, "code_verifier": verifier,
    })
    if r.status_code >= 400:
        raise SSOError("exchange", r.text[:200])
    return r.json()


def _signing_key(id_token: str):
    uri = discovery()["jwks_uri"]
    if uri not in _jwks:
        _jwks[uri] = jwt.PyJWKClient(uri, cache_keys=True)
    return _jwks[uri].get_signing_key_from_jwt(id_token).key


def finish(code: str | None, state: str | None, flow_cookie: str | None) -> str:
    """Complete the flow; returns the verified e-mail address."""
    s = get_settings()
    if not code or not state or not flow_cookie:
        raise SSOError("missing")
    try:
        flow = jwt.decode(flow_cookie, s.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise SSOError("expired")
    if not secrets.compare_digest(flow["state"], state):
        raise SSOError("state")

    id_token = _exchange(code, flow["verifier"]).get("id_token")
    if not id_token:
        raise SSOError("exchange", "no id_token")
    try:
        claims = jwt.decode(
            id_token, _signing_key(id_token), algorithms=["RS256"],
            audience=s.oidc_client_id, issuer=discovery()["issuer"],
            options={"require": ["exp", "iat", "iss", "aud", "nonce"]})
    except jwt.PyJWTError as exc:
        raise SSOError("token", str(exc))
    if not secrets.compare_digest(claims.get("nonce", ""), flow["nonce"]):
        raise SSOError("token", "nonce")

    # Entra puts the address in preferred_username when "email" is not
    # released; either is the user principal name in this tenant
    email = claims.get("email") or claims.get("preferred_username") or claims.get("upn")
    if not email or "@" not in email:
        raise SSOError("email")
    return email.strip().lower()
