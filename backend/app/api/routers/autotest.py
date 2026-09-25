"""Browser scenarios: write them, draft them from free text, run them.

A run is its own process (app/autotest/runner.py); this only starts it and
reads back what it wrote. Scenario editing needs write_cases, running one
needs write_results -- the same split as cases and results.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...autotest import ai, variables
from ...autotest.dsl import help_lines, parse
from ...config import get_settings
from ...db import get_session
from ...models import AutoRun, AutoScenario, AutoVariable, Case, Run, Test, User
from ..deps import current_user
from ..permissions import (WRITE_CASES, WRITE_RESULTS, assert_can, assert_read,
                           project_of)

router = APIRouter(prefix="/api", tags=["autotest"])

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
# run id -> the runner process, to tell "still going" from "died"
_procs: dict[int, subprocess.Popen] = {}


def launch(run_id: int) -> None:
    """Start the runner. Replaced in the tests, which have no browser."""
    env = dict(os.environ)
    env["PYTHONPATH"] = BACKEND + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    _procs[run_id] = subprocess.Popen(
        [sys.executable, "-m", "app.autotest.runner", str(run_id)],
        cwd=os.getcwd(), env=env)


def _now():
    return datetime.now(timezone.utc)


def _name(session: Session, user_id: int | None) -> str | None:
    return session.get(User, user_id).name if user_id and session.get(User, user_id) else None


def _run_out(session: Session, r: AutoRun, full: bool = True) -> dict:
    proc = _procs.get(r.id)
    if r.status in ("queued", "running") and proc is not None and proc.poll() is not None:
        # the runner exited without writing an ending: it crashed
        session.refresh(r)
        if r.status in ("queued", "running"):
            r.status, r.finished_on = "error", _now()
            r.message = r.message or "koşturucu beklenmedik şekilde kapandı"
            session.commit()
    out = {
        "id": r.id, "scenario_id": r.scenario_id, "status": r.status,
        "message": r.message, "created_on": r.created_on,
        "started_on": r.started_on, "finished_on": r.finished_on,
        "started_by": _name(session, r.started_by),
        "test_id": r.test_id, "result_id": r.result_id,
        "passed": sum(1 for x in r.log or [] if x.get("status") == "passed"),
        "total": len(r.log or []),
    }
    if full:
        out["log"] = r.log or []
        out["steps"] = r.steps
    return out


def _scenario(session: Session, user: User, scenario_id: int) -> AutoScenario:
    s = session.get(AutoScenario, scenario_id)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bulunamadi")
    assert_read(session, user, s.project_id)
    return s


def _case_title(session: Session, case_id: int | None) -> str | None:
    case = session.get(Case, case_id) if case_id else None
    return case.title if case else None


def _scenario_out(session: Session, s: AutoScenario, last: AutoRun | None = None) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "name": s.name,
        "description": s.description, "steps": s.steps,
        "case_id": s.case_id, "case_title": _case_title(session, s.case_id),
        "updated_on": s.updated_at, "updated_by": _name(session, s.updated_by),
        "last_run": _run_out(session, last, full=False) if last else None,
    }


# --- language ------------------------------------------------------------------

@router.get("/autotest/config")
def config(_: User = Depends(current_user)):
    settings = get_settings()
    return {"ai": ai.enabled(), "headless": settings.autotest_headless,
            "commands": help_lines()}


class Check(BaseModel):
    steps: str = Field(max_length=50_000)
    project_id: int | None = None


@router.post("/autotest/check")
def check(body: Check, user: User = Depends(current_user),
          session: Session = Depends(get_session)):
    steps, errors = parse(body.steps)
    out = [{"line": e.line, "message": e.message} for e in errors]
    if body.project_id is not None:
        assert_read(session, user, body.project_id)
        known = set(session.scalars(select(AutoVariable.name).where(
            AutoVariable.project_id == body.project_id)))
        for number, line in enumerate(body.steps.splitlines(), 1):
            for name in sorted(variables.referenced(line) - known):
                out.append({"line": number,
                            "message": "tanımsız değişken: {{" + name + "}}"})
    out.sort(key=lambda e: e["line"])
    return {"count": len(steps), "errors": out}


class Draft(BaseModel):
    project_id: int
    text: str = Field(min_length=3, max_length=8000)
    start_url: str | None = None


@router.post("/autotest/draft")
def draft(body: Draft, user: User = Depends(current_user),
          session: Session = Depends(get_session)):
    assert_read(session, user, body.project_id)
    assert_can(session, user, WRITE_CASES, body.project_id)
    try:
        return ai.draft(body.text, body.start_url)
    except ai.AIError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None


# --- scenarios -----------------------------------------------------------------

class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    steps: str = Field(default="", max_length=50_000)
    case_id: int | None = None


class ScenarioPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    steps: str | None = Field(default=None, max_length=50_000)
    case_id: int | None = None


def _check_case(session: Session, project_id: int, case_id: int | None) -> None:
    if case_id is not None and project_of(session, case=case_id) != project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "case bu projede bulunamadı")


@router.get("/projects/{project_id}/autotest/scenarios")
def list_scenarios(project_id: int, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    assert_read(session, user, project_id)
    rows = session.scalars(select(AutoScenario).where(AutoScenario.project_id == project_id)
                           .order_by(AutoScenario.name)).all()
    last_ids = dict(session.execute(
        select(AutoRun.scenario_id, func.max(AutoRun.id))
        .where(AutoRun.scenario_id.in_([s.id for s in rows] or [0]))
        .group_by(AutoRun.scenario_id)).all())
    lasts = {r.scenario_id: r for r in session.scalars(
        select(AutoRun).where(AutoRun.id.in_(list(last_ids.values()) or [0])))}
    return [_scenario_out(session, s, lasts.get(s.id)) for s in rows]


@router.post("/projects/{project_id}/autotest/scenarios", status_code=201)
def create_scenario(project_id: int, body: ScenarioIn, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    assert_read(session, user, project_id)
    assert_can(session, user, WRITE_CASES, project_id)
    _check_case(session, project_id, body.case_id)
    s = AutoScenario(project_id=project_id, name=body.name.strip(),
                     description=body.description, steps=body.steps,
                     case_id=body.case_id, created_by=user.id, updated_by=user.id)
    session.add(s)
    session.commit()
    return _scenario_out(session, s)


@router.get("/autotest/scenarios/{scenario_id}")
def get_scenario(scenario_id: int, user: User = Depends(current_user),
                 session: Session = Depends(get_session)):
    return _scenario_out(session, _scenario(session, user, scenario_id))


@router.patch("/autotest/scenarios/{scenario_id}")
def update_scenario(scenario_id: int, body: ScenarioPatch, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    s = _scenario(session, user, scenario_id)
    assert_can(session, user, WRITE_CASES, s.project_id)
    changes = body.model_dump(exclude_unset=True)
    if "case_id" in changes:
        _check_case(session, s.project_id, changes["case_id"])
    for key, value in changes.items():
        setattr(s, key, value.strip() if key == "name" else value)
    s.updated_by = user.id
    session.commit()
    return _scenario_out(session, s)


@router.delete("/autotest/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: int, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    s = _scenario(session, user, scenario_id)
    assert_can(session, user, WRITE_CASES, s.project_id)
    session.delete(s)
    session.commit()


# --- runs ----------------------------------------------------------------------

class StartRun(BaseModel):
    # a test in a run: the outcome is written there as a result
    test_id: int | None = None


@router.post("/autotest/scenarios/{scenario_id}/runs", status_code=201)
def start_run(scenario_id: int, body: StartRun | None = None,
              user: User = Depends(current_user),
              session: Session = Depends(get_session)):
    s = _scenario(session, user, scenario_id)
    assert_can(session, user, WRITE_RESULTS, s.project_id)
    test_id = body.test_id if body else None
    if test_id is not None:
        test = session.get(Test, test_id)
        owner = session.get(Run, test.run_id) if test else None
        if owner is None or owner.project_id != s.project_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "test bu projede bulunamadı")
        if owner.is_archived:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "arşivlenmiş koşuma sonuç eklenemez")
    _, errors = parse(s.steps)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "; ".join(f"{e.line}. satır: {e.message}" for e in errors))
    busy = session.scalar(select(AutoRun).where(
        AutoRun.scenario_id == s.id, AutoRun.status.in_(("queued", "running"))))
    if busy is not None:
        _run_out(session, busy, full=False)       # clears one whose runner died
        if busy.status in ("queued", "running"):
            raise HTTPException(status.HTTP_409_CONFLICT, "bu senaryo zaten koşuyor")
    run = AutoRun(scenario_id=s.id, status="queued", steps=s.steps, log=[],
                  test_id=test_id, started_by=user.id, created_on=_now())
    session.add(run)
    session.commit()
    try:
        launch(run.id)
    except OSError as e:
        run.status, run.message, run.finished_on = "error", f"başlatılamadı: {e}", _now()
        session.commit()
    return _run_out(session, run)


@router.get("/autotest/scenarios/{scenario_id}/runs")
def list_runs(scenario_id: int, user: User = Depends(current_user),
              session: Session = Depends(get_session)):
    s = _scenario(session, user, scenario_id)
    rows = session.scalars(select(AutoRun).where(AutoRun.scenario_id == s.id)
                           .order_by(AutoRun.id.desc()).limit(30)).all()
    return [_run_out(session, r, full=False) for r in rows]


def _run(session: Session, user: User, run_id: int) -> tuple[AutoRun, AutoScenario]:
    r = session.get(AutoRun, run_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bulunamadi")
    return r, _scenario(session, user, r.scenario_id)


@router.get("/autotest/runs/{run_id}")
def get_run(run_id: int, user: User = Depends(current_user),
            session: Session = Depends(get_session)):
    r, _ = _run(session, user, run_id)
    return _run_out(session, r)


@router.post("/autotest/runs/{run_id}/stop")
def stop_run(run_id: int, user: User = Depends(current_user),
             session: Session = Depends(get_session)):
    r, s = _run(session, user, run_id)
    assert_can(session, user, WRITE_RESULTS, s.project_id)
    if r.status in ("queued", "running"):
        r.stop_requested = True
        proc = _procs.get(r.id)
        if r.status == "queued" and (proc is None or proc.poll() is not None):
            r.status, r.finished_on = "stopped", _now()
        session.commit()
    return _run_out(session, r)


@router.get("/autotest/runs/{run_id}/shots/{index}")
def shot(run_id: int, index: int, user: User = Depends(current_user),
         session: Session = Depends(get_session)):
    _run(session, user, run_id)
    path = os.path.join(get_settings().storage_dir, "autotest", str(run_id), f"{index}.png")
    if not os.path.isfile(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bulunamadi")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})


@router.get("/cases/{case_id}/autotest")
def scenarios_for_case(case_id: int, user: User = Depends(current_user),
                       session: Session = Depends(get_session)):
    """The scenarios that automate a case, for the test panel of a run."""
    project_id = project_of(session, case=case_id)
    assert_read(session, user, project_id)
    rows = session.scalars(select(AutoScenario).where(AutoScenario.case_id == case_id)
                           .order_by(AutoScenario.name)).all()
    out = []
    for sc in rows:
        last = session.scalar(select(AutoRun).where(AutoRun.scenario_id == sc.id)
                              .order_by(AutoRun.id.desc()).limit(1))
        out.append({"id": sc.id, "name": sc.name,
                    "last_run": _run_out(session, last, full=False) if last else None})
    return out


# --- variables -------------------------------------------------------------------

class VariableIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    value: str = Field(default="", max_length=4000)
    is_secret: bool = False


class VariablePatch(BaseModel):
    value: str | None = Field(default=None, max_length=4000)
    is_secret: bool | None = None


def _variable_out(session: Session, v: AutoVariable) -> dict:
    readable = not v.is_secret or variables.unseal(v.value) is not None
    return {"id": v.id, "name": v.name, "is_secret": v.is_secret,
            # a secret never goes back to the page
            "value": None if v.is_secret else v.value,
            "has_value": bool(v.value), "readable": readable,
            "updated_on": v.updated_at, "updated_by": _name(session, v.updated_by)}


@router.get("/projects/{project_id}/autotest/variables")
def list_variables(project_id: int, user: User = Depends(current_user),
                   session: Session = Depends(get_session)):
    assert_read(session, user, project_id)
    rows = session.scalars(select(AutoVariable).where(AutoVariable.project_id == project_id)
                           .order_by(AutoVariable.name)).all()
    return [_variable_out(session, v) for v in rows]


@router.post("/projects/{project_id}/autotest/variables", status_code=201)
def create_variable(project_id: int, body: VariableIn, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    assert_read(session, user, project_id)
    assert_can(session, user, WRITE_CASES, project_id)
    name = body.name.strip()
    if not variables.NAME.match(name):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "ad harf ya da _ ile başlamalı; yalnız harf, rakam ve _ içerebilir")
    if session.scalar(select(AutoVariable).where(AutoVariable.project_id == project_id,
                                                 AutoVariable.name == name)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{name} zaten var")
    v = AutoVariable(project_id=project_id, name=name, is_secret=body.is_secret,
                     value=variables.seal(body.value) if body.is_secret else body.value,
                     updated_by=user.id)
    session.add(v)
    session.commit()
    return _variable_out(session, v)


def _variable(session: Session, user: User, variable_id: int) -> AutoVariable:
    v = session.get(AutoVariable, variable_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bulunamadi")
    assert_read(session, user, v.project_id)
    assert_can(session, user, WRITE_CASES, v.project_id)
    return v


@router.patch("/autotest/variables/{variable_id}")
def update_variable(variable_id: int, body: VariablePatch, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    v = _variable(session, user, variable_id)
    secret = v.is_secret if body.is_secret is None else body.is_secret
    if body.value is not None:
        plain = body.value
    elif secret == v.is_secret:
        plain = None                                  # nothing to re-store
    elif v.is_secret:
        # a secret made ordinary would show its value; ask for it again
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "gizli değeri açık yapmak için değeri yeniden girin")
    else:
        plain = v.value
    if plain is not None:
        v.value = variables.seal(plain) if secret else plain
    v.is_secret = secret
    v.updated_by = user.id
    session.commit()
    return _variable_out(session, v)


@router.delete("/autotest/variables/{variable_id}", status_code=204)
def delete_variable(variable_id: int, user: User = Depends(current_user),
                    session: Session = Depends(get_session)):
    v = _variable(session, user, variable_id)
    session.delete(v)
    session.commit()
