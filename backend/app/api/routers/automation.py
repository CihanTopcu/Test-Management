"""The machine-facing surface: API tokens and bulk result reporting.

Shaped so an existing TestRail client needs a base URL and a credential
change, not a rewrite: results are posted per run, keyed by case id, in one
call. The RTTS jobs push thousands of results a week; one request per test
would be both slow and a good way to half-write a run.
"""
import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import ApiToken, Case, Result, Run, Suite, Test, User
from ..deps import current_user
from ..permissions import WRITE_CASES, WRITE_RESULTS, assert_can

router = APIRouter(prefix="/api", tags=["automation"])


# --- token management (browser session) -------------------------------------

class TokenCreate(BaseModel):
    name: str
    expires_days: int | None = None


class TokenOut(BaseModel):
    id: int
    name: str
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.get("/tokens", response_model=list[TokenOut])
def list_tokens(session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    rows = session.scalars(
        select(ApiToken).where(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc())).all()
    return [TokenOut(id=t.id, name=t.name, prefix=t.prefix,
                     is_active=t.is_active, created_at=t.created_at,
                     last_used_at=t.last_used_at, expires_at=t.expires_at)
            for t in rows]


@router.post("/tokens", status_code=201)
def create_token(payload: TokenCreate, session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    raw = "tm_" + secrets.token_urlsafe(32)
    prefix = raw[:12]
    expires = None
    if payload.expires_days:
        expires = datetime.now(timezone.utc).replace(microsecond=0)
        expires = expires.fromtimestamp(
            expires.timestamp() + payload.expires_days * 86400, tz=timezone.utc)

    token = ApiToken(user_id=user.id, name=payload.name, prefix=prefix,
                     token_hash=_hash(raw), expires_at=expires)
    session.add(token)
    session.commit()
    # the only time the plaintext exists outside the caller's hands
    return {"id": token.id, "name": token.name, "token": raw,
            "prefix": prefix,
            "note": "Bu değer bir daha gösterilmeyecek, şimdi kaydedin."}


@router.delete("/tokens/{token_id}", status_code=204)
def revoke_token(token_id: int, session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    token = session.get(ApiToken, token_id)
    if token is None or token.user_id != user.id:
        raise HTTPException(404, "token bulunamadi")
    token.is_active = False
    session.commit()


# --- token authentication (machines) ----------------------------------------

def token_user(user: User = Depends(current_user)) -> User:
    """Kept as a name for the machine-facing routes.

    Authentication itself lives in deps.current_user, which understands API
    tokens, JWTs and the session cookie alike -- a CI job needs to read a
    case before it can report a result on it.
    """
    return user


# --- bulk result reporting --------------------------------------------------

class ResultForCase(BaseModel):
    case_id: int
    status_id: int
    comment: str | None = None
    version: str | None = None
    elapsed: str | None = None
    defects: str | None = None


class BulkResults(BaseModel):
    results: list[ResultForCase] = Field(min_length=1)


@router.post("/runs/{run_id}/results", status_code=201)
def add_results_for_cases(run_id: int, payload: BulkResults,
                          session: Session = Depends(get_session),
                          user: User = Depends(token_user)):
    """Post many results at once, addressed by case id.

    Mirrors TestRail's add_results_for_cases so existing jobs only have to
    change the base URL and the credential.
    """
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RESULTS, run.project_id)
    if run.is_completed:
        raise HTTPException(400, "tamamlanmis kosuma sonuc eklenemez")

    tests = {t.case_id: t for t in session.scalars(
        select(Test).where(Test.run_id == run_id))}

    now = datetime.now(timezone.utc)
    created, unknown = [], []
    for item in payload.results:
        test = tests.get(item.case_id)
        if test is None:
            unknown.append(item.case_id)
            continue
        result = Result(
            test_id=test.id, status_id=item.status_id, created_by=user.id,
            created_on=now, comment=item.comment, version=item.version,
            elapsed=item.elapsed, defects=item.defects, custom={},
        )
        session.add(result)
        test.status_id = item.status_id
        created.append(item.case_id)
    session.commit()

    return {"run_id": run_id, "created": len(created),
            "unknown_case_ids": unknown,
            "detail": "kosumda bulunmayan case'ler atlandi" if unknown else None}


class BulkTestStatus(BaseModel):
    test_ids: list[int] = Field(min_length=1)
    status_id: int
    comment: str | None = None


@router.post("/runs/{run_id}/bulk-status", status_code=201)
def set_status_for_tests(run_id: int, payload: BulkTestStatus,
                         session: Session = Depends(get_session),
                         user: User = Depends(token_user)):
    """Mark a selection of tests in one go -- the 'select all, mark passed'
    action every tester asks for on day one."""
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RESULTS, run.project_id)
    tests = session.scalars(
        select(Test).where(Test.run_id == run_id,
                           Test.id.in_(payload.test_ids))).all()
    now = datetime.now(timezone.utc)
    for test in tests:
        session.add(Result(test_id=test.id, status_id=payload.status_id,
                           created_by=user.id, created_on=now,
                           comment=payload.comment, custom={}))
        test.status_id = payload.status_id
    session.commit()
    return {"updated": len(tests)}


# --- bulk case edits --------------------------------------------------------

class BulkCaseUpdate(BaseModel):
    case_ids: list[int] = Field(min_length=1)
    type_id: int | None = None
    priority_id: int | None = None
    section_id: int | None = None
    milestone_id: int | None = None
    refs: str | None = None


@router.post("/cases/bulk-update")
def bulk_update_cases(payload: BulkCaseUpdate,
                      session: Session = Depends(get_session),
                      user: User = Depends(current_user)):
    cases = session.scalars(
        select(Case).where(Case.id.in_(payload.case_ids))).all()
    if cases:
        suite = session.get(Suite, cases[0].suite_id)
        assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)
    fields = payload.model_dump(exclude_unset=True, exclude={"case_ids"})
    if not fields:
        raise HTTPException(400, "degistirilecek alan verilmedi")

    now = datetime.now(timezone.utc)
    for case in cases:
        for key, value in fields.items():
            setattr(case, key, value)
        case.updated_by = user.id
        case.updated_on = now
    session.commit()
    return {"updated": len(cases), "fields": list(fields)}
