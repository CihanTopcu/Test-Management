"""Project-level roll-ups: the numbers the overview screens are made of."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, CaseHistory, Milestone, Project, ProjectMember,
                       Result, Run, Section, Suite, Test, User)
from ..deps import current_user
from ..schemas import ActivityItem, ProjectStats, TodoItem

router = APIRouter(prefix="/api", tags=["overview"])

# TestRail's own ids, which this instance kept. "Failed" is one status out of
# nine, not "everything that is not passed" -- a run holding two deferred
# tests must not be reported as a run holding two failures.
PASSED, UNTESTED, FAILED = 1, 3, 5


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
        passed = status.get(str(PASSED), 0)
        untested = status.get(str(UNTESTED), 0) + status.get("untested", 0)
        failed = status.get(str(FAILED), 0)
        items.append({
            "project_id": project.id,
            "name": project.name,
            "is_completed": project.is_completed,
            "cases": cases.get(project.id, 0),
            "active_runs": active_runs.get(project.id, 0),
            "tests": tests,
            "passed": passed,
            "failed": failed,
            "other": max(0, tests - passed - untested - failed),
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


@router.get("/today")
def today(runs: int = Query(8, ge=1, le=50),
          session: Session = Depends(get_session),
          user: User = Depends(current_user)):
    """The work in front of the signed-in person, right now.

    The application used to open on project statistics, which tell you how
    things are but never what to do. This is the other question, and it is
    the one somebody opening a test tool at 09:00 actually has.

    Four sections, in the order they matter: what is assigned to me, runs I
    started and have not finished, what broke since yesterday in projects I
    work in, and milestones about to come due. One endpoint rather than four
    calls, because the whole point is that the page is there before you have
    decided to wait for it.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=1)

    # --- assigned to me, still unanswered ---------------------------------
    assigned_rows = session.execute(
        select(Project.id, Project.name, Run.id, Run.name,
               func.count(Test.id))
        .select_from(Test)
        .join(Run, Test.run_id == Run.id)
        .join(Project, Run.project_id == Project.id)
        .where(Test.assignedto_id == user.id,
               Run.is_completed.is_(False), Run.is_archived.is_(False),
               (Test.status_id.is_(None)) | (Test.status_id == 3))
        .group_by(Project.id, Project.name, Run.id, Run.name)
        .order_by(func.count(Test.id).desc())
        .limit(12)).all()

    assigned = [{"project_id": pid, "project_name": pname,
                 "run_id": rid, "run_name": rname, "pending": n}
                for pid, pname, rid, rname, n in assigned_rows]

    # --- runs that moved recently -----------------------------------------
    # Not "runs I started": in this instance runs are opened by automation,
    # so scoping to created_by returns nothing for everyone. What people
    # actually want to see is what has been running.
    # No date floor. A cut-over instance can sit quiet for weeks, and a
    # section that empties itself on exactly those mornings is the section
    # nobody trusts. The row carries how long ago it was instead.
    recent = session.execute(
        select(Test.run_id, func.max(Result.created_on))
        .join(Result, Result.test_id == Test.id)
        .group_by(Test.run_id)
        .order_by(func.max(Result.created_on).desc())
        .limit(runs)).all()
    recent_ids = [r for r, _ in recent]
    last_seen = {r: at for r, at in recent}

    my_runs = []
    if recent_ids:
        progress = (
            select(Test.run_id,
                   func.count().label("total"),
                   func.count().filter(Test.status_id == PASSED).label("passed"),
                   func.count().filter(Test.status_id == FAILED).label("failed"),
                   func.count().filter(
                       (Test.status_id.is_(None)) | (Test.status_id == UNTESTED)
                   ).label("untested"))
            .where(Test.run_id.in_(recent_ids))
            .group_by(Test.run_id).subquery())

        rows = session.execute(
            select(Run.id, Run.name, Project.id, Project.name,
                   progress.c.total, progress.c.passed, progress.c.failed,
                   progress.c.untested, Run.is_completed)
            .join(Project, Run.project_id == Project.id)
            .join(progress, progress.c.run_id == Run.id)
            .where(Run.id.in_(recent_ids))).all()

        order = {rid: i for i, rid in enumerate(recent_ids)}
        for rid, rname, pid, pname, total, passed, failed, untested, done in rows:
            my_runs.append({
                "run_id": rid, "run_name": rname,
                "project_id": pid, "project_name": pname,
                "total": total, "untested": untested,
                "passed": passed,
                "failed": failed,
                "other": max(0, total - passed - untested - failed),
                "done": total - untested,
                "percent": round(100 * (total - untested) / total) if total else 0,
                "is_completed": done,
                "last_result_on": last_seen.get(rid),
            })
        my_runs.sort(key=lambda r: order.get(r["run_id"], 99))

    # --- what broke since yesterday ---------------------------------------
    # Scoped to projects the person is a member of; with no membership rows
    # at all that would hide everything, so an unscoped account sees all.
    member_of = [m for (m,) in session.execute(
        select(ProjectMember.project_id)
        .where(ProjectMember.user_id == user.id)).all()]

    failure_where = [Result.created_on >= since, Result.status_id == 5,
                     Run.is_archived.is_(False)]
    if member_of:
        failure_where.append(Run.project_id.in_(member_of))

    failure_rows = session.execute(
        select(Project.id, Project.name, Run.id, Run.name, Test.id,
               Test.title, Result.created_on, User.name)
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .join(Project, Run.project_id == Project.id)
        .outerjoin(User, Result.created_by == User.id)
        .where(*failure_where)
        .order_by(Result.created_on.desc())
        .limit(15)).all()

    failures = [{"project_id": pid, "project_name": pname,
                 "run_id": rid, "run_name": rname, "test_id": tid,
                 "title": title, "at": at, "by": by}
                for pid, pname, rid, rname, tid, title, at, by in failure_rows]

    total_failures = session.scalar(
        select(func.count()).select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(*failure_where)) or 0

    # --- milestones about to come due --------------------------------------
    # Bounded on both sides. Something due in the next week is a plan; one
    # that slipped four years ago is a cleanup task and does not belong on
    # a page about today.
    horizon = now + timedelta(days=7)
    floor = now - timedelta(days=60)
    ms_where = [Milestone.is_completed.is_(False),
                Milestone.due_on.is_not(None), Milestone.due_on <= horizon,
                Milestone.due_on >= floor]
    if member_of:
        ms_where.append(Milestone.project_id.in_(member_of))

    ms_rows = session.execute(
        select(Milestone.id, Milestone.name, Milestone.due_on,
               Project.id, Project.name)
        .join(Project, Milestone.project_id == Project.id)
        .where(*ms_where)
        .order_by(Milestone.due_on)
        .limit(10)).all()

    milestones = [{
        "milestone_id": mid, "name": name, "due_on": due,
        "project_id": pid, "project_name": pname,
        "days": (due - now).days,
    } for mid, name, due, pid, pname in ms_rows]

    # --- the projects this person works in ---------------------------------
    # Sixteen of them; a strip of one-click entries is the thing that makes
    # this page worth opening on a morning when nothing else moved.
    project_where = []
    if member_of:
        project_where.append(Project.id.in_(member_of))
    project_rows = session.execute(
        select(Project.id, Project.name)
        .where(Project.is_completed.is_(False), *project_where)
        .order_by(Project.name)).all()

    case_counts = dict(session.execute(
        select(Suite.project_id, func.count())
        .join(Case, Case.suite_id == Suite.id)
        .where(Case.is_deleted.is_(False))
        .group_by(Suite.project_id)).all())
    open_runs = dict(session.execute(
        select(Run.project_id, func.count())
        .where(Run.is_archived.is_(False), Run.is_completed.is_(False))
        .group_by(Run.project_id)).all())

    projects = [{"project_id": pid, "name": name,
                 "cases": case_counts.get(pid, 0),
                 "open_runs": open_runs.get(pid, 0)}
                for pid, name in project_rows]

    return {
        "user": {"id": user.id, "name": user.name},
        "generated_on": now,
        "projects": projects,
        "assigned": assigned,
        "assigned_total": sum(a["pending"] for a in assigned),
        "my_runs": my_runs,
        "failures": failures,
        "failures_total": total_failures,
        "milestones": milestones,
        "scoped_to_memberships": bool(member_of),
        # said out loud so an empty page is explained rather than just empty
        "assignment_in_use": bool(session.scalar(
            select(func.count()).select_from(Test)
            .where(Test.assignedto_id.is_not(None)).limit(1))),
    }
