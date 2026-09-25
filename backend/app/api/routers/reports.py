"""Reports.

TestRail ships dozens of report templates; these are the ones this team's
data can actually answer today, built from what was imported rather than
from a list of report names.

The later three exist because the migrated data turned out to say something
uncomfortable: 7,722 cases both pass and fail repeatedly, 4,146 are
duplicates of a case in the same folder, and a third of the library has
never been run at all.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, CaseType, CustomField, CustomFieldOption,
                       Priority, Result, Run, Section, Suite, Test, User)
from ..deps import current_user
from ..schemas import DistributionOut, SeriesPoint
from ..permissions import read_project

# every report is about one project, so one guard covers them all
router = APIRouter(prefix="/api/projects/{project_id}/reports", tags=["reports"],
                   dependencies=[Depends(read_project)])


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

    # the id travels with the bucket so the bar can become a link: a
    # distribution nobody can click into is a number you have to go and
    # reproduce by hand
    rows = session.execute(
        select(model.id, label_col, func.count())
        .select_from(Case)
        .outerjoin(model, column == model.id)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False))
        .group_by(model.id, label_col)
        .order_by(func.count().desc())).all()

    buckets = [{"id": bucket_id, "label": name or "Belirsiz", "count": n}
               for bucket_id, name, n in rows]
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
        select(Suite.id, Suite.name, func.count(Case.id))
        .join(Case, Case.suite_id == Suite.id)
        .where(Suite.project_id == project_id, Case.is_deleted.is_(False))
        .group_by(Suite.id, Suite.name)
        .order_by(func.count(Case.id).desc())).all()

    return {
        "cases": total,
        "with_refs": with_refs,
        "executed": executed,
        "by_suite": [{"id": sid, "label": name, "count": n}
                     for sid, name, n in by_suite],
    }


@router.get("/flaky")
def flaky(project_id: int, days: int = 90,
          min_each: int = Query(3, ge=2, le=50),
          limit: int = Query(50, le=200),
          session: Session = Depends(get_session),
          _: User = Depends(current_user)):
    """Cases that both pass and fail repeatedly.

    A test that flaps costs more than a failing one: people learn to re-run
    it rather than read it, and after a while nobody trusts a red run at all.

    Windowed on purpose. A case that flapped in 2022 and has been steady
    since is not today's problem, and scoping to the recent past also keeps
    the query off most of the 1.09M results.
    """
    since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    passed = func.count().filter(Result.status_id == 1)
    failed = func.count().filter(Result.status_id == 5)

    where = [Result.created_on >= since, Result.status_id.in_([1, 5]),
             Run.project_id == project_id]

    rows = session.execute(
        select(Case.id, Case.title, Case.suite_id, passed, failed,
               func.max(Result.created_on))
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .join(Case, Test.case_id == Case.id)
        .where(*where)
        .group_by(Case.id, Case.title, Case.suite_id)
        .having(passed >= min_each)
        .having(failed >= min_each)
        .order_by(func.least(passed, failed).desc())
        .limit(limit)).all()

    return {
        "days": days,
        "min_each": min_each,
        "items": [{
            "case_id": cid, "title": title, "suite_id": suite_id,
            "passed": p, "failed": f, "runs": p + f,
            # how often it changed its mind, which reads better than a count
            "flip_rate": round(100 * min(p, f) / (p + f)),
            "last_seen": last,
        } for cid, title, suite_id, p, f, last in rows],
    }


@router.get("/duplicates")
def duplicates(project_id: int, limit: int = Query(50, le=200),
               session: Session = Depends(get_session),
               _: User = Depends(current_user)):
    """Cases with the same title in the same section.

    Two cases with one name in one folder are either a copy somebody forgot
    to rename or the same scenario written twice; both waste a tester's time
    every run. Titles are compared case-insensitively and trimmed, because
    that is how the duplicates in this data actually differ.
    """
    suite_ids = select(Suite.id).where(
        Suite.project_id == project_id).scalar_subquery()
    key = func.lower(func.btrim(Case.title))

    rows = session.execute(
        select(Case.section_id, key, func.count(),
               func.array_agg(aggregate_order_by(Case.id, Case.id)),
               func.min(Case.title))
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False))
        .group_by(Case.section_id, key)
        .having(func.count() > 1)
        .order_by(func.count().desc())
        .limit(limit)).all()

    names = dict(session.execute(
        select(Section.id, Section.name)
        .where(Section.id.in_([r[0] for r in rows]))).all()) if rows else {}

    return {"items": [{
        "section_id": section_id,
        "section_name": names.get(section_id, "?"),
        "title": title,
        "count": count,
        "case_ids": ids[:20],
    } for section_id, _key, count, ids, title in rows]}


@router.get("/never-run")
def never_run(project_id: int, offset: int = 0,
              limit: int = Query(100, le=500),
              session: Session = Depends(get_session),
              _: User = Depends(current_user)):
    """Active cases that have never appeared in a run.

    Not a fault in itself -- some cases are written ahead of a feature -- but
    a third of this library has never been executed, and a case nobody runs
    is a case nobody maintains.
    """
    suite_ids = select(Suite.id).where(
        Suite.project_id == project_id).scalar_subquery()
    unused = ~select(Test.id).where(Test.case_id == Case.id).exists()

    total = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False), unused))
    rows = session.execute(
        select(Case.id, Case.title, Case.section_id, Case.created_on)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False), unused)
        .order_by(Case.id).offset(offset).limit(limit)).all()

    names = dict(session.execute(
        select(Section.id, Section.name)
        .where(Section.id.in_([r[2] for r in rows]))).all()) if rows else {}

    return {
        "total": total, "offset": offset, "limit": limit,
        "items": [{"case_id": cid, "title": title, "section_id": sid,
                   "section_name": names.get(sid, "?"), "created_on": created}
                  for cid, title, sid, created in rows],
    }


# The team already keeps this backlog in a custom field; these are the values
# that mean "somebody still runs this by hand".
MANUAL_LABELS = {"ready to automation", "non-automated", "manuel test",
                 "not done", "partial automation"}


@router.get("/automation-backlog")
def automation_backlog(project_id: int, limit: int = Query(50, le=200),
                       session: Session = Depends(get_session),
                       _: User = Depends(current_user)):
    """Cases still run by hand, most-executed first.

    The team already tracks this in the IsAutomated field -- 2,544 cases sit
    at "Ready to Automation". What the field cannot tell them is which ones
    to do first, and the answer is in the execution history: automating the
    case somebody has run 109 times pays back immediately, the one run twice
    does not.
    """
    field = session.scalar(
        select(CustomField).where(CustomField.entity == "case",
                                  CustomField.system_name.in_(
                                      ["custom_automation_type",
                                       "custom_isautomated"])))
    if field is None:
        return {"configured": False, "by_status": [], "items": [],
                "detail": "Bu instance'ta otomasyon durumu alanı tanımlı değil."}

    options = session.execute(
        select(CustomFieldOption.value, CustomFieldOption.label)
        .where(CustomFieldOption.field_id == field.id)).all()
    labels = {str(value): label for value, label in options}
    manual_values = [v for v, label in labels.items()
                     if label.strip().lower() in MANUAL_LABELS]

    suite_ids = select(Suite.id).where(
        Suite.project_id == project_id).scalar_subquery()
    value = Case.custom[field.system_name].astext

    spread = session.execute(
        select(value, func.count())
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False))
        .group_by(value).order_by(func.count().desc())).all()

    by_status = [{
        "value": raw,
        "label": labels.get(raw, "(belirtilmemiş)" if raw is None else f"#{raw}"),
        "count": count,
        "is_manual": raw in manual_values,
    } for raw, count in spread]

    if not manual_values:
        return {"configured": True, "by_status": by_status, "items": [],
                "detail": "Bu projede elle koşulan olarak işaretli case yok."}

    runs = func.count(Test.id)
    rows = session.execute(
        select(Case.id, Case.title, value, runs, func.max(Result.created_on))
        .select_from(Case)
        .join(Test, Test.case_id == Case.id)
        .outerjoin(Result, Result.test_id == Test.id)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False),
               value.in_(manual_values))
        .group_by(Case.id, Case.title, value)
        .order_by(runs.desc())
        .limit(limit)).all()

    items = [{"case_id": cid, "title": title,
              "status": labels.get(raw, raw), "runs": n, "last_run": last}
             for cid, title, raw, n, last in rows]
    payload = {
        "configured": True,
        "field_label": field.label,
        "by_status": by_status,
        "items": items,
    }
    if not items:
        # An empty table with no explanation reads like a broken report.
        # Two different nothings land here: nothing marked manual at all, and
        # manual cases that have simply never been run -- the ranking is by
        # execution count, so those cannot appear.
        marked = sum(s["count"] for s in by_status if s["is_manual"])
        payload["detail"] = (
            f"{marked} case elle koşulan olarak işaretli ama hiçbiri bir"
            " koşuma girmemiş; bu liste koşum sayısına göre sıralanıyor."
            if marked else
            "Bu projede elle koşulan olarak işaretli case yok.")
    return payload
