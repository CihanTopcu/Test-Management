"""Project-level roll-ups: the numbers the overview screens are made of."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, CaseHistory, Milestone, Project, Result, Run,
                       Section, Suite, Test, User)
from ..deps import current_user
from ..schemas import ActivityItem, ProjectStats, TodoItem

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/projects/{project_id}/stats", response_model=ProjectStats)
def project_stats(project_id: int, session: Session = Depends(get_session),
                  _: User = Depends(current_user)):
    """One query set instead of the six round trips the UI would otherwise make."""
    suite_ids = select(Suite.id).where(Suite.project_id == project_id).scalar_subquery()

    suites = session.scalar(
        select(func.count()).select_from(Suite).where(Suite.project_id == project_id))
    sections = session.scalar(
        select(func.count()).select_from(Section).where(Section.suite_id.in_(suite_ids)))
    cases = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False)))

    runs = session.scalar(
        select(func.count()).select_from(Run).where(Run.project_id == project_id))
    active_runs = session.scalar(
        select(func.count()).select_from(Run)
        .where(Run.project_id == project_id, Run.is_completed.is_(False),
               Run.is_archived.is_(False)))
    archived_runs = session.scalar(
        select(func.count()).select_from(Run)
        .where(Run.project_id == project_id, Run.is_archived.is_(True)))

    milestones = session.scalar(
        select(func.count()).select_from(Milestone)
        .where(Milestone.project_id == project_id))
    open_milestones = session.scalar(
        select(func.count()).select_from(Milestone)
        .where(Milestone.project_id == project_id,
               Milestone.is_completed.is_(False)))

    rows = session.execute(
        select(Test.status_id, func.count())
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id == project_id)
        .group_by(Test.status_id)).all()

    return ProjectStats(
        project_id=project_id, suites=suites, sections=sections, cases=cases,
        runs=runs, active_runs=active_runs, archived_runs=archived_runs,
        milestones=milestones,
        open_milestones=open_milestones,
        tests=sum(n for _, n in rows),
        by_status={str(s) if s is not None else "untested": n for s, n in rows},
    )


@router.get("/projects/{project_id}/activity", response_model=list[ActivityItem])
def project_activity(project_id: int, limit: int = 25,
                     session: Session = Depends(get_session),
                     _: User = Depends(current_user)):
    """Most recent result entries across the project."""
    rows = session.execute(
        select(Run.id, Run.name, Test.id, Test.title, Result.status_id,
               Result.created_on, Result.created_by)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id == project_id)
        .order_by(Result.created_on.desc())
        .limit(limit)).all()
    return [ActivityItem(run_id=r[0], run_name=r[1], test_id=r[2],
                         test_title=r[3], status_id=r[4], created_on=r[5],
                         created_by=r[6]) for r in rows]


@router.get("/todo", response_model=list[TodoItem])
def my_todo(limit: int = 200, session: Session = Depends(get_session),
            user: User = Depends(current_user)):
    """Tests assigned to the signed-in user that still need a result.

    Deliberately across every project: people work in several at once and the
    point of a to-do list is not having to go looking.
    """
    rows = session.execute(
        select(Project.id, Project.name, Run.id, Run.name, Test.id,
               Test.title, Test.status_id)
        .join(Run, Test.run_id == Run.id)
        .join(Project, Run.project_id == Project.id)
        .where(Test.assignedto_id == user.id,
               Run.is_completed.is_(False),
               (Test.status_id.is_(None)) | (Test.status_id == 3))
        .order_by(Project.name, Run.name)
        .limit(limit)).all()
    return [TodoItem(project_id=r[0], project_name=r[1], run_id=r[2],
                     run_name=r[3], test_id=r[4], test_title=r[5],
                     status_id=r[6]) for r in rows]


@router.get("/dashboard")
def dashboard(days: int = 30, session: Session = Depends(get_session),
              user: User = Depends(current_user)):
    """Every project on one screen.

    The team runs 16 projects and the only way to compare them was to open
    each overview in turn. One query per metric across all projects, rather
    than one round trip per project: at 13,929 runs and 1.06M tests the
    per-project loop was the expensive part, not the aggregation.

    Archived runs are left out of the activity figures on purpose -- they are
    release history, and including them would make every project look busy.
    """
    since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    projects = session.scalars(
        select(Project).order_by(Project.name)).all()
    names = {p.id: p.name for p in projects}

    cases = dict(session.execute(
        select(Suite.project_id, func.count())
        .join(Case, Case.suite_id == Suite.id)
        .where(Case.is_deleted.is_(False))
        .group_by(Suite.project_id)).all())

    active_runs = dict(session.execute(
        select(Run.project_id, func.count())
        .where(Run.is_archived.is_(False), Run.is_completed.is_(False))
        .group_by(Run.project_id)).all())

    # status roll-up over live runs only
    status_rows = session.execute(
        select(Run.project_id, Test.status_id, func.count())
        .join(Test, Test.run_id == Run.id)
        .where(Run.is_archived.is_(False))
        .group_by(Run.project_id, Test.status_id)).all()
    by_project: dict[int, dict[str, int]] = {}
    for pid, status_id, count in status_rows:
        key = str(status_id) if status_id is not None else "untested"
        by_project.setdefault(pid, {})[key] = count

    recent = dict(session.execute(
        select(Run.project_id, func.count())
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(Result.created_on >= since)
        .group_by(Run.project_id)).all())

    open_milestones = dict(session.execute(
        select(Milestone.project_id, func.count())
        .where(Milestone.is_completed.is_(False))
        .group_by(Milestone.project_id)).all())

    overdue = dict(session.execute(
        select(Milestone.project_id, func.count())
        .where(Milestone.is_completed.is_(False),
               Milestone.due_on.is_not(None),
               Milestone.due_on < datetime.now(timezone.utc))
        .group_by(Milestone.project_id)).all())

    items = []
    for project in projects:
        status = by_project.get(project.id, {})
        tests = sum(status.values())
        passed = status.get("1", 0)
        untested = status.get("3", 0) + status.get("untested", 0)
        items.append({
            "project_id": project.id,
            "name": project.name,
            "is_completed": project.is_completed,
            "cases": cases.get(project.id, 0),
            "active_runs": active_runs.get(project.id, 0),
            "tests": tests,
            "passed": passed,
            "failed": max(0, tests - passed - untested),
            "untested": untested,
            "pass_rate": round(100 * passed / tests) if tests else None,
            "results_in_window": recent.get(project.id, 0),
            "open_milestones": open_milestones.get(project.id, 0),
            "overdue_milestones": overdue.get(project.id, 0),
        })

    return {
        "days": days,
        "generated_on": datetime.now(timezone.utc),
        "totals": {
            "projects": len(projects),
            "cases": sum(cases.values()),
            "active_runs": sum(active_runs.values()),
            "results_in_window": sum(recent.values()),
            "open_milestones": sum(open_milestones.values()),
            "overdue_milestones": sum(overdue.values()),
        },
        "projects": items,
        "names": names,
    }


@router.get("/activity-by-user")
def activity_by_user(days: int = 90, project_id: int | None = None,
                     session: Session = Depends(get_session),
                     _: User = Depends(current_user)):
    """Who did what, across the instance.

    A caution that belongs with the numbers rather than in a wiki page: in
    the migrated data five of the six active accounts are shared team
    logins, named after the domain they cover, and the sixth carries the
    automation's API key. So this measures how much work each *domain*
    produced, not how much each person did -- and the activity mix is the
    only honest way to tell a person from a robot here. An account that
    only ever posts results is a pipeline; one that writes and edits cases
    is somebody at a keyboard.
    """
    since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))

    def scoped(query, run_join=True):
        if project_id is None:
            return query
        return query.where(Run.project_id == project_id) if run_join else query

    # One pass over the result table, grouped by account and project; the
    # per-account totals are summed from it. Asking twice -- once for totals,
    # once for the project spread -- doubled a query that already walks 1.09M
    # rows, and took the all-time view to ten seconds.
    spread_rows = session.execute(scoped(
        select(Result.created_by, Project.name, func.count())
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .join(Project, Run.project_id == Project.id)
        .where(Result.created_on >= since)
        .group_by(Result.created_by, Project.name))).all()

    results: dict[int, int] = {}
    spread: dict[int, list] = {}
    for uid, name, count in spread_rows:
        results[uid] = results.get(uid, 0) + count
        spread.setdefault(uid, []).append({"project": name, "results": count})

    suite_filter = []
    if project_id is not None:
        suite_filter.append(Suite.project_id == project_id)

    created = dict(session.execute(
        select(Case.created_by, func.count())
        .join(Suite, Case.suite_id == Suite.id)
        .where(Case.created_on >= since, *suite_filter)
        .group_by(Case.created_by)).all())

    edited = dict(session.execute(
        select(CaseHistory.user_id, func.count())
        .join(Case, CaseHistory.case_id == Case.id)
        .join(Suite, Case.suite_id == Suite.id)
        .where(CaseHistory.created_on >= since, *suite_filter)
        .group_by(CaseHistory.user_id)).all())

    runs = dict(session.execute(scoped(
        select(Run.created_by, func.count())
        .where(Run.created_on >= since)
        .group_by(Run.created_by))).all())

    people = {u.id: u for u in session.scalars(select(User))}
    items = []
    for uid in set(results) | set(created) | set(edited) | set(runs):
        if uid is None:
            continue
        user = people.get(uid)
        counts = {
            "results": results.get(uid, 0),
            "cases_created": created.get(uid, 0),
            "cases_edited": edited.get(uid, 0),
            "runs_created": runs.get(uid, 0),
        }
        total = sum(counts.values())
        if not total:
            continue
        authoring = counts["cases_created"] + counts["cases_edited"]
        items.append({
            "user_id": uid,
            "name": user.name if user else f"#{uid}",
            "email": user.email if user else None,
            "is_active": bool(user and user.is_active),
            **counts,
            "total": total,
            # the share of work that is not result-posting; a pipeline sits
            # near zero, a person does not
            "authoring_share": round(100 * authoring / total),
            "projects": sorted(spread.get(uid, []),
                               key=lambda p: -p["results"])[:5],
        })

    items.sort(key=lambda i: -i["total"])
    return {
        "days": days,
        "since": since,
        "totals": {
            "results": sum(i["results"] for i in items),
            "cases_created": sum(i["cases_created"] for i in items),
            "cases_edited": sum(i["cases_edited"] for i in items),
            "runs_created": sum(i["runs_created"] for i in items),
            "accounts": len(items),
        },
        "items": items,
    }
