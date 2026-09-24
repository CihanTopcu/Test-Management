"""Test plans: several runs executed together as one campaign.

TestRail's model is plan -> entry -> run, where one entry fans out into a run
per configuration (browser, environment, bank). The imported data only has a
single plan, but the structure is how regression campaigns are organised, and
without it every run has to be created and tracked by hand.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...audit import record
from ...db import get_session
from ...models import (Attachment, Case, Plan, PlanEntry, Result, Run, Suite,
                       Test, User)
from ..deps import current_user
from ..permissions import WRITE_RUNS, assert_can

router = APIRouter(prefix="/api", tags=["plans"])


class PlanEntryIn(BaseModel):
    suite_id: int
    name: str | None = None
    include_all: bool = True
    case_ids: list[int] = Field(default_factory=list)
    section_ids: list[int] = Field(default_factory=list)
    # one run is created per configuration; empty means a single plain run
    configs: list[str] = Field(default_factory=list)
    assignedto_id: int | None = None


class PlanCreate(BaseModel):
    name: str
    description: str | None = None
    milestone_id: int | None = None
    assignedto_id: int | None = None
    entries: list[PlanEntryIn] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    milestone_id: int | None = None
    assignedto_id: int | None = None
    is_completed: bool | None = None


def _select_cases(session: Session, entry: PlanEntryIn) -> list[Case]:
    where = [Case.suite_id == entry.suite_id, Case.is_deleted.is_(False)]
    if not entry.include_all:
        if entry.case_ids:
            where.append(Case.id.in_(entry.case_ids))
        elif entry.section_ids:
            where.append(Case.section_id.in_(entry.section_ids))
        else:
            return []
    return list(session.scalars(select(Case).where(*where)))


def _make_run(session: Session, plan: Plan, entry_row: PlanEntry,
              cases: list[Case], name: str, config: str | None,
              assignedto_id: int | None, user_id: int) -> Run:
    run = Run(
        project_id=plan.project_id, suite_id=entry_row.suite_id,
        plan_entry_id=entry_row.id, milestone_id=plan.milestone_id,
        name=name, config=config, config_ids=[], include_all=False,
        assignedto_id=assignedto_id, created_by=user_id,
        created_on=datetime.now(timezone.utc),
    )
    session.add(run)
    session.flush()
    session.add_all([
        Test(run_id=run.id, case_id=c.id, title=c.title, status_id=3,
             type_id=c.type_id, priority_id=c.priority_id,
             template_id=c.template_id, milestone_id=c.milestone_id,
             refs=c.refs, estimate=c.estimate, custom=dict(c.custom or {}),
             assignedto_id=assignedto_id)
        for c in cases])
    return run


@router.get("/projects/{project_id}/plans")
def list_plans(project_id: int, session: Session = Depends(get_session),
               _: User = Depends(current_user)):
    plans = session.scalars(
        select(Plan).where(Plan.project_id == project_id)
        .order_by(Plan.created_on.desc().nulls_last())).all()
    if not plans:
        return []

    # progress for the whole plan in one pass rather than per run
    rows = session.execute(
        select(PlanEntry.plan_id, Test.status_id, func.count())
        .join(Run, Run.plan_entry_id == PlanEntry.id)
        .join(Test, Test.run_id == Run.id)
        .where(PlanEntry.plan_id.in_([p.id for p in plans]))
        .group_by(PlanEntry.plan_id, Test.status_id)).all()
    tally: dict[int, dict[str, int]] = {}
    for plan_id, status_id, n in rows:
        slot = tally.setdefault(
            plan_id, {"total": 0, "passed": 0, "failed": 0, "untested": 0})
        slot["total"] += n
        if status_id == 1:
            slot["passed"] += n
        elif status_id == 5:
            slot["failed"] += n
        elif status_id is None or status_id == 3:
            slot["untested"] += n

    entry_counts = dict(session.execute(
        select(PlanEntry.plan_id, func.count())
        .where(PlanEntry.plan_id.in_([p.id for p in plans]))
        .group_by(PlanEntry.plan_id)).all())

    return [{
        "id": p.id, "name": p.name, "description": p.description,
        "milestone_id": p.milestone_id, "is_completed": p.is_completed,
        "created_on": p.created_on, "created_by": p.created_by,
        "assignedto_id": p.assignedto_id,
        "entry_count": entry_counts.get(p.id, 0),
        "test_count": tally.get(p.id, {}).get("total", 0),
        "passed_count": tally.get(p.id, {}).get("passed", 0),
        "failed_count": tally.get(p.id, {}).get("failed", 0),
        "untested_count": tally.get(p.id, {}).get("untested", 0),
    } for p in plans]


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, session: Session = Depends(get_session),
             _: User = Depends(current_user)):
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "plan bulunamadi")

    entries = session.scalars(
        select(PlanEntry).where(PlanEntry.plan_id == plan_id)
        .order_by(PlanEntry.display_order)).all()
    runs = session.scalars(
        select(Run).where(Run.plan_entry_id.in_([e.id for e in entries]))).all() \
        if entries else []

    counts: dict[int, dict[str, int]] = {}
    if runs:
        for run_id, status_id, n in session.execute(
                select(Test.run_id, Test.status_id, func.count())
                .where(Test.run_id.in_([r.id for r in runs]))
                .group_by(Test.run_id, Test.status_id)):
            slot = counts.setdefault(
                run_id, {"total": 0, "passed": 0, "failed": 0, "untested": 0})
            slot["total"] += n
            if status_id == 1:
                slot["passed"] += n
            elif status_id == 5:
                slot["failed"] += n
            elif status_id is None or status_id == 3:
                slot["untested"] += n

    suites = {s.id: s.name for s in session.scalars(
        select(Suite).where(Suite.project_id == plan.project_id))}

    return {
        "id": plan.id, "project_id": plan.project_id, "name": plan.name,
        "description": plan.description, "milestone_id": plan.milestone_id,
        "assignedto_id": plan.assignedto_id, "is_completed": plan.is_completed,
        "created_on": plan.created_on, "created_by": plan.created_by,
        "entries": [{
            "id": e.id, "name": e.name, "suite_id": e.suite_id,
            "suite_name": suites.get(e.suite_id, ""),
            "runs": [{
                "id": r.id, "name": r.name, "config": r.config,
                "is_completed": r.is_completed,
                "test_count": counts.get(r.id, {}).get("total", 0),
                "passed_count": counts.get(r.id, {}).get("passed", 0),
                "failed_count": counts.get(r.id, {}).get("failed", 0),
                "untested_count": counts.get(r.id, {}).get("untested", 0),
            } for r in runs if r.plan_entry_id == e.id],
        } for e in entries],
    }


@router.post("/projects/{project_id}/plans", status_code=201)
def create_plan(project_id: int, payload: PlanCreate,
                session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    assert_can(session, user, WRITE_RUNS, project_id)
    plan = Plan(
        project_id=project_id, name=payload.name,
        description=payload.description, milestone_id=payload.milestone_id,
        assignedto_id=payload.assignedto_id, created_by=user.id,
        created_on=datetime.now(timezone.utc),
    )
    session.add(plan)
    session.flush()

    created_runs = 0
    for order, entry in enumerate(payload.entries):
        suite = session.get(Suite, entry.suite_id)
        entry_row = PlanEntry(
            plan_id=plan.id, suite_id=entry.suite_id,
            name=entry.name or (suite.name if suite else f"Entry {order + 1}"),
            display_order=order,
        )
        session.add(entry_row)
        session.flush()

        cases = _select_cases(session, entry)
        configs = entry.configs or [None]
        for config in configs:
            label = entry_row.name + (f" ({config})" if config else "")
            _make_run(session, plan, entry_row, cases, label, config,
                      entry.assignedto_id, user.id)
            created_runs += 1

    session.commit()
    return {"id": plan.id, "name": plan.name, "entries": len(payload.entries),
            "runs": created_runs}


@router.post("/plans/{plan_id}/entries", status_code=201)
def add_entry(plan_id: int, entry: PlanEntryIn,
              session: Session = Depends(get_session),
              user: User = Depends(current_user)):
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "plan bulunamadi")
    assert_can(session, user, WRITE_RUNS, plan.project_id)
    order = session.scalar(
        select(func.coalesce(func.max(PlanEntry.display_order), -1))
        .where(PlanEntry.plan_id == plan_id)) + 1

    suite = session.get(Suite, entry.suite_id)
    entry_row = PlanEntry(plan_id=plan.id, suite_id=entry.suite_id,
                          name=entry.name or (suite.name if suite else "Entry"),
                          display_order=order)
    session.add(entry_row)
    session.flush()

    cases = _select_cases(session, entry)
    runs = 0
    for config in (entry.configs or [None]):
        label = entry_row.name + (f" ({config})" if config else "")
        _make_run(session, plan, entry_row, cases, label, config,
                  entry.assignedto_id, user.id)
        runs += 1
    session.commit()
    return {"entry_id": entry_row.id, "runs": runs, "cases": len(cases)}


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(plan_id: int, request: Request,
                session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    """Delete a plan together with the runs it fanned out into.

    A plan's runs exist only because the plan created them -- plan_entries
    cascades to runs in the schema -- so leaving them behind would produce
    orphan runs nobody can find. Archived plans are release history and are
    refused, as archived runs are.
    """
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "plan bulunamadi")
    assert_can(session, user, WRITE_RUNS, plan.project_id)
    if plan.is_archived:
        raise HTTPException(400, "arsivlenmis plan silinemez")

    entries = list(session.scalars(
        select(PlanEntry.id).where(PlanEntry.plan_id == plan_id)))
    runs = list(session.scalars(
        select(Run.id).where(Run.plan_entry_id.in_(entries)))) if entries else []
    if runs:
        archived = session.scalar(
            select(func.count()).select_from(Run)
            .where(Run.id.in_(runs), Run.is_archived.is_(True))) or 0
        if archived:
            raise HTTPException(
                400, f"plandaki {archived} kosum arsivde, plan silinemez")
        tests = list(session.scalars(select(Test.id).where(Test.run_id.in_(runs))))
        if tests:
            results = list(session.scalars(
                select(Result.id).where(Result.test_id.in_(tests))))
            if results:
                session.execute(Attachment.__table__.delete().where(
                    Attachment.entity_type == "result",
                    Attachment.entity_id.in_(results)))
    record(session, user, "delete", "plan", plan_id, label=plan.name,
           project_id=plan.project_id, request=request,
           detail={"runs": len(runs)})
    session.delete(plan)
    session.commit()


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: int, payload: PlanUpdate,
                session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise HTTPException(404, "plan bulunamadi")
    assert_can(session, user, WRITE_RUNS, plan.project_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_completed") and not plan.completed_on:
        plan.completed_on = datetime.now(timezone.utc)
    if data.get("is_completed") is False:
        plan.completed_on = None
    for key, value in data.items():
        setattr(plan, key, value)
    session.commit()
    return {"id": plan.id, "is_completed": plan.is_completed}
