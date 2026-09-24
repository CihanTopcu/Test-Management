"""Building the scheduled digests.

Three digests, chosen because they answer questions people actually ask each
morning rather than because they were easy to compute:

  summary     where each project stands, and whether anything moved
  failures    what failed since the last one -- the QA lead's first question
  milestones  what is due soon or already late

Each builder returns (subject, body) or None. Returning None is normal and
important: a digest with nothing in it should not be sent. Nobody reads the
fourth "no failures" e-mail, and by the fifth they filter the sender.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (Case, Milestone, Project, Result, Run, Suite, Test, User)

WINDOW = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


def _projects_for(session: Session, subscription) -> list[Project]:
    if subscription.project_id:
        project = session.get(Project, subscription.project_id)
        return [project] if project else []
    return list(session.scalars(
        select(Project).where(Project.is_completed.is_(False))
        .order_by(Project.name)))


def _since(subscription, now: datetime) -> datetime:
    """The window this digest covers.

    Measured from the last delivery rather than a fixed period, so a digest
    that failed to send yesterday reports two days of work instead of
    silently dropping a day.
    """
    if subscription.last_sent_on:
        return subscription.last_sent_on
    return now - WINDOW.get(subscription.frequency, WINDOW["daily"])


def build(session: Session, subscription, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    builder = {"summary": _summary, "failures": _failures,
               "milestones": _milestones}.get(subscription.kind)
    if builder is None:
        return None
    return builder(session, subscription, now)


def _summary(session: Session, subscription, now: datetime):
    since = _since(subscription, now)
    projects = _projects_for(session, subscription)
    if not projects:
        return None
    ids = [p.id for p in projects]

    results = dict(session.execute(
        select(Run.project_id, func.count())
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .where(Run.project_id.in_(ids), Result.created_on >= since)
        .group_by(Run.project_id)).all())

    if not results:
        return None  # nothing happened; say nothing

    active = dict(session.execute(
        select(Run.project_id, func.count())
        .where(Run.project_id.in_(ids), Run.is_archived.is_(False),
               Run.is_completed.is_(False))
        .group_by(Run.project_id)).all())

    status = session.execute(
        select(Run.project_id, Test.status_id, func.count())
        .join(Test, Test.run_id == Run.id)
        .where(Run.project_id.in_(ids), Run.is_archived.is_(False))
        .group_by(Run.project_id, Test.status_id)).all()
    rollup: dict[int, dict] = {}
    for pid, status_id, count in status:
        rollup.setdefault(pid, {})[status_id] = count

    lines = [f"{_window_label(since, now)} özeti:", ""]
    for project in projects:
        moved = results.get(project.id, 0)
        if not moved:
            continue
        counts = rollup.get(project.id, {})
        total = sum(counts.values())
        passed = counts.get(1, 0)
        rate = f"%{round(100 * passed / total)}" if total else "—"
        lines.append(
            f"• {project.name}: {moved} sonuç girildi · "
            f"{active.get(project.id, 0)} devam eden koşum · geçme {rate}")

    return "Test özeti", "\n".join(lines)


def _failures(session: Session, subscription, now: datetime):
    since = _since(subscription, now)
    projects = _projects_for(session, subscription)
    if not projects:
        return None
    ids = [p.id for p in projects]

    rows = session.execute(
        select(Project.name, Run.id, Run.name, Test.id, Test.title,
               User.name, Result.created_on, Result.defects)
        .select_from(Result)
        .join(Test, Result.test_id == Test.id)
        .join(Run, Test.run_id == Run.id)
        .join(Project, Run.project_id == Project.id)
        .outerjoin(User, Result.created_by == User.id)
        .where(Run.project_id.in_(ids), Result.created_on >= since,
               Result.status_id == 5)
        .order_by(Project.name, Run.id, Result.created_on.desc())
        .limit(200)).all()

    if not rows:
        return None

    by_run: dict[tuple, list] = {}
    for pname, run_id, run_name, test_id, title, who, when, defects in rows:
        by_run.setdefault((pname, run_id, run_name), []).append(
            (test_id, title, who, defects))

    lines = [f"{_window_label(since, now)} içinde {len(rows)} başarısız test:", ""]
    for (pname, run_id, run_name), failures in by_run.items():
        lines.append(f"{pname} — R{run_id} {run_name} ({len(failures)})")
        for test_id, title, who, defects in failures[:10]:
            suffix = f" · hata {defects}" if defects else ""
            lines.append(f"   T{test_id} {title[:70]}"
                         f" — {who or 'bilinmeyen'}{suffix}")
        if len(failures) > 10:
            lines.append(f"   … ve {len(failures) - 10} test daha")
        lines.append("")

    if len(rows) == 200:
        lines.append("(listede ilk 200 sonuç var)")
    return f"{len(rows)} başarısız test", "\n".join(lines).strip()


def _milestones(session: Session, subscription, now: datetime):
    projects = _projects_for(session, subscription)
    if not projects:
        return None
    ids = [p.id for p in projects]
    horizon = now + timedelta(days=7)

    rows = session.execute(
        select(Project.name, Milestone.id, Milestone.name, Milestone.due_on)
        .join(Project, Milestone.project_id == Project.id)
        .where(Milestone.project_id.in_(ids),
               Milestone.is_completed.is_(False),
               Milestone.due_on.is_not(None),
               Milestone.due_on <= horizon)
        .order_by(Milestone.due_on)).all()

    if not rows:
        return None

    late = [r for r in rows if r[3] < now]
    soon = [r for r in rows if r[3] >= now]

    lines = []
    if late:
        lines.append(f"Tarihi geçmiş ({len(late)}):")
        for pname, mid, name, due in late:
            days = (now - due).days
            lines.append(f"   {pname} — {name} · {days} gün gecikti")
        lines.append("")
    if soon:
        lines.append(f"Bu hafta ({len(soon)}):")
        for pname, mid, name, due in soon:
            days = (due - now).days
            lines.append(f"   {pname} — {name} · {days} gün kaldı")

    subject = (f"{len(late)} milestone gecikti" if late
               else f"{len(soon)} milestone bu hafta")
    return subject, "\n".join(lines).strip()


def _window_label(since: datetime, now: datetime) -> str:
    hours = (now - since).total_seconds() / 3600
    if hours <= 26:
        return "Son 24 saat"
    return f"Son {round(hours / 24)} gün"


def is_due(subscription, now: datetime) -> bool:
    """Has this subscription's moment arrived, and not been served already?

    The hour is a floor, not an exact match: a scheduler that runs every
    fifteen minutes, or a container that was down at 08:00, should still
    deliver rather than skip the day entirely.
    """
    if not subscription.is_active:
        return False
    if now.hour < subscription.hour:
        return False
    if subscription.frequency == "weekly" and now.weekday() != subscription.weekday:
        return False

    last = subscription.last_sent_on
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    # one per calendar day at most, whatever the scheduler's cadence
    return last.date() < now.date()
