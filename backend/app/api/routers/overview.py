"""Project-level roll-ups: the numbers the overview screens are made of."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, Milestone, Project, Result, Run, Section, Suite,
                       Test, User)
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
