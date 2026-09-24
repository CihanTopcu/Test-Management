"""Reports.

TestRail ships dozens of report templates; these are the four this team's
data can actually answer today, built from what was imported rather than from
a list of report names.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, CaseType, Priority, Result, Run, Suite, Test,
                       User)
from ..deps import current_user
from ..schemas import DistributionOut, SeriesPoint

router = APIRouter(prefix="/api/projects/{project_id}/reports", tags=["reports"])


@router.get("/property-distribution", response_model=DistributionOut)
def property_distribution(project_id: int,
                          by: str = Query("type", pattern="^(type|priority)$"),
                          session: Session = Depends(get_session),
                          _: User = Depends(current_user)):
    """How the case library splits across type or priority."""
    suite_ids = select(Suite.id).where(Suite.project_id == project_id).scalar_subquery()
    if by == "type":
        column, model, label_col = Case.type_id, CaseType, CaseType.name
    else:
        column, model, label_col = Case.priority_id, Priority, Priority.name

    rows = session.execute(
        select(label_col, func.count())
        .select_from(Case)
        .outerjoin(model, column == model.id)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False))
        .group_by(label_col)
        .order_by(func.count().desc())).all()

    buckets = [{"label": name or "Belirsiz", "count": n} for name, n in rows]
    return DistributionOut(
        title="Case tipi dağılımı" if by == "type" else "Öncelik dağılımı",
        buckets=buckets, total=sum(b["count"] for b in buckets))


@router.get("/activity", response_model=list[SeriesPoint])
def activity(project_id: int, days: int = 90,
             session: Session = Depends(get_session),
             _: User = Depends(current_user)):
    """Results entered per day, split by status."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = session.execute(
        select(func.date(Result.created_on), Result.status_id, func.count())
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id == project_id, Result.created_on >= since)
        .group_by(func.date(Result.created_on), Result.status_id)
        .order_by(func.date(Result.created_on))).all()

    per_day: dict[str, dict[str, int]] = defaultdict(dict)
    for day, status_id, n in rows:
        per_day[str(day)][str(status_id) if status_id else "untested"] = n
    return [SeriesPoint(label=day, values=values)
            for day, values in sorted(per_day.items())]


@router.get("/defects")
def defects(project_id: int, limit: int = 40,
            session: Session = Depends(get_session),
            _: User = Depends(current_user)):
    """Defect references seen in results, most cited first.

    TestRail stores these as a free-text field, so one result can name several
    tickets; they are split here rather than counted as one string.
    """
    rows = session.execute(
        select(Result.defects, Result.status_id, Test.title, Run.id, Run.name)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id == project_id, Result.defects.is_not(None),
               Result.defects != "")).all()

    tally: dict[str, dict] = {}
    for defect_field, status_id, title, run_id, run_name in rows:
        for ref in str(defect_field).replace(";", ",").split(","):
            ref = ref.strip()
            if not ref:
                continue
            slot = tally.setdefault(ref, {"ref": ref, "count": 0, "tests": []})
            slot["count"] += 1
            if len(slot["tests"]) < 5:
                slot["tests"].append({"title": title, "run_id": run_id,
                                      "run_name": run_name,
                                      "status_id": status_id})
    ordered = sorted(tally.values(), key=lambda d: -d["count"])[:limit]
    return {"total": len(tally), "items": ordered}


@router.get("/coverage")
def coverage(project_id: int, session: Session = Depends(get_session),
             _: User = Depends(current_user)):
    """How much of the library is linked to a requirement, and how much of it
    has ever been executed."""
    suite_ids = select(Suite.id).where(Suite.project_id == project_id).scalar_subquery()

    total = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False)))
    with_refs = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False),
               Case.refs.is_not(None), Case.refs != ""))
    executed = session.scalar(
        select(func.count(func.distinct(Test.case_id)))
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id == project_id, Test.case_id.is_not(None)))

    by_suite = session.execute(
        select(Suite.name, func.count(Case.id))
        .join(Case, Case.suite_id == Suite.id)
        .where(Suite.project_id == project_id, Case.is_deleted.is_(False))
        .group_by(Suite.name).order_by(func.count(Case.id).desc())).all()

    return {
        "cases": total,
        "with_refs": with_refs,
        "executed": executed,
        "by_suite": [{"label": name, "count": n} for name, n in by_suite],
    }
