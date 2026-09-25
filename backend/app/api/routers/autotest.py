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

from ...autotest import ai
from ...autotest.dsl import help_lines, parse
from ...config import get_settings
from ...db import get_session
from ...models import AutoRun, AutoScenario, User
from ..deps import current_user
from ..permissions import WRITE_CASES, WRITE_RESULTS, assert_can, assert_read

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


def _scenario_out(session: Session, s: AutoScenario, last: AutoRun | None = None) -> dict:
    return {
        "id": s.id, "project_id": s.project_id, "name": s.name,
        "description": s.description, "steps": s.steps,
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


@router.post("/autotest/check")
def check(body: Check, _: User = Depends(current_user)):
    steps, errors = parse(body.steps)
    return {"count": len(steps),
            "errors": [{"line": e.line, "message": e.message} for e in errors]}


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


class ScenarioPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=8000)
    steps: str | None = Field(default=None, max_length=50_000)


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
    s = AutoScenario(project_id=project_id, name=body.name.strip(),
                     description=body.description, steps=body.steps,
                     created_by=user.id, updated_by=user.id)
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
    for key, value in body.model_dump(exclude_unset=True).items():
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

@router.post("/autotest/scenarios/{scenario_id}/runs", status_code=201)
def start_run(scenario_id: int, user: User = Depends(current_user),
              session: Session = Depends(get_session)):
    s = _scenario(session, user, scenario_id)
    assert_can(session, user, WRITE_RESULTS, s.project_id)
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
                  started_by=user.id, created_on=_now())
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
