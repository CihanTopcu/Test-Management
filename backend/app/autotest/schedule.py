"""Plans: scenarios that run by themselves.

The API process keeps a small thread that looks every half minute for plans
that are due. Claiming one is a single UPDATE conditioned on the next_run_at
it read, so two API processes -- or a restart mid-tick -- never fire the
same plan twice. A plan missed while nothing was running fires once when
the clock comes back, not once per missed slot.
"""
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from .dsl import parse
from .variables import parse_data

log = logging.getLogger(__name__)
TIME = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
TICK_SECONDS = 30
DAY_NAMES = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]


def zone() -> ZoneInfo:
    return ZoneInfo(get_settings().autotest_timezone)


def next_fire(days: list[int], times: list[str], after: datetime) -> datetime | None:
    """The first slot strictly after `after`, or None for an empty schedule."""
    slots = sorted({(int(m.group(1)), int(m.group(2)))
                    for t in times if (m := TIME.match(t.strip()))})
    days = sorted({d for d in days if 0 <= d <= 6})
    if not slots or not days:
        return None
    local = after.astimezone(zone())
    for offset in range(8):
        day = (local + timedelta(days=offset)).date()
        if day.weekday() not in days:
            continue
        for h, m in slots:
            at = datetime(day.year, day.month, day.day, h, m, tzinfo=zone())
            if at > local:
                return at.astimezone(timezone.utc)
    return None


def fire(session: Session, plan, trigger: str, user_id: int | None) -> "object":
    """Queue the plan's scenarios as one batch and start the runner."""
    from ..api.routers import autotest as api
    from ..models import AutoBatch, AutoRun, AutoScenario, Case, Run, Test

    now = datetime.now(timezone.utc)
    batch = AutoBatch(project_id=plan.project_id, plan_id=plan.id, trigger=trigger,
                      started_by=user_id, created_on=now, run_ids=[], summary={})
    session.add(batch)
    session.flush()

    scenarios = session.scalars(select(AutoScenario).where(
        AutoScenario.id.in_(plan.scenario_ids or [0]),
        AutoScenario.project_id == plan.project_id)).all()
    order = {sid: i for i, sid in enumerate(plan.scenario_ids or [])}
    scenarios = sorted(scenarios, key=lambda s: order.get(s.id, 0))

    # a test run per suite the linked cases live in, holding just those cases
    test_of: dict[int, int] = {}
    if plan.record_run:
        cases = session.scalars(select(Case).where(
            Case.id.in_([s.case_id for s in scenarios if s.case_id] or [0]),
            Case.is_deleted.is_(False))).all()
        by_suite: dict[int, list] = {}
        for c in cases:
            by_suite.setdefault(c.suite_id, []).append(c)
        stamp = now.astimezone(zone()).strftime("%d.%m.%Y %H:%M")
        for suite_id, group in by_suite.items():
            run = Run(project_id=plan.project_id, suite_id=suite_id,
                      name=f"{plan.name} · otomasyon · {stamp}",
                      description=f"Otomasyon planı \"{plan.name}\" tarafından açıldı.",
                      include_all=False, created_by=user_id or plan.created_by,
                      created_on=now, config_ids=[])
            session.add(run)
            session.flush()
            batch.run_ids = [*batch.run_ids, run.id]
            for c in group:
                test = Test(run_id=run.id, case_id=c.id, title=c.title, status_id=3,
                            type_id=c.type_id, priority_id=c.priority_id,
                            template_id=c.template_id, milestone_id=c.milestone_id,
                            refs=c.refs, estimate=c.estimate, custom=dict(c.custom or {}))
                session.add(test)
                session.flush()
                test_of[c.id] = test.id

    queued, skipped = [], []
    for s in scenarios:
        _, errors = parse(s.steps)
        _, data_error = parse_data(s.data)
        if errors or data_error:
            skipped.append(s.name)
            continue
        r = AutoRun(scenario_id=s.id, status="queued", steps=s.steps, log=[],
                    test_id=test_of.get(s.case_id) if s.case_id else None,
                    batch_id=batch.id, started_by=user_id or plan.created_by,
                    created_on=now)
        session.add(r)
        queued.append(r)
    batch.summary = {"queued": len(queued), "skipped": skipped}
    plan.last_run_at = now
    if not queued:
        batch.finished_on = now
    session.commit()
    if queued:
        try:
            api.launch(*[r.id for r in queued])
        except OSError as e:
            for r in queued:
                r.status, r.message, r.finished_on = "error", f"başlatılamadı: {e}", now
            session.commit()
            finish_batch(session, batch.id)
    return batch


def finish_batch(session: Session, batch_id: int) -> None:
    """Called after each run of a batch ends; the last one closes the batch
    and tells the plan's people how it went."""
    from ..models import AutoBatch, AutoPlan, AutoRun, AutoScenario
    from ..notifications import notify

    batch = session.get(AutoBatch, batch_id)
    if batch is None or batch.finished_on is not None:
        return
    runs = session.scalars(select(AutoRun).where(AutoRun.batch_id == batch_id)).all()
    if any(r.status in ("queued", "running") for r in runs):
        return
    counts = {k: sum(1 for r in runs if r.status == k)
              for k in ("passed", "failed", "error", "stopped")}
    batch.summary = {**(batch.summary or {}), **counts}
    batch.finished_on = datetime.now(timezone.utc)

    plan = session.get(AutoPlan, batch.plan_id) if batch.plan_id else None
    bad = counts["failed"] + counts["error"]
    if plan is not None and (bad or plan.notify_always):
        names = {s.id: s.name for s in session.scalars(select(AutoScenario).where(
            AutoScenario.id.in_([r.scenario_id for r in runs] or [0])))}
        failing = [names.get(r.scenario_id, "?") for r in runs if r.status in ("failed", "error")]
        subject = (f"Otomasyon: {plan.name} — {bad} senaryo kaldı" if bad
                   else f"Otomasyon: {plan.name} — hepsi geçti")
        body = (f"{counts['passed']} geçti, {counts['failed']} kaldı, {counts['error']} hata."
                + ("\n\nKalanlar:\n- " + "\n- ".join(failing[:20]) if failing else ""))
        link = (f"/#/p/{plan.project_id}/runs/{batch.run_ids[0]}" if batch.run_ids
                else f"/#/p/{plan.project_id}/autotest?tab=plans&plan={plan.id}")
        for uid in plan.notify_user_ids or []:
            notify(session, uid, "automation", subject, body, link=link)
    session.commit()


def tick(session: Session, now: datetime | None = None) -> list[int]:
    """Fire every active plan that is due. Returns the batch ids."""
    from ..models import AutoPlan

    now = now or datetime.now(timezone.utc)
    fired = []
    due = session.scalars(select(AutoPlan).where(
        AutoPlan.is_active.is_(True), AutoPlan.next_run_at.is_not(None),
        AutoPlan.next_run_at <= now)).all()
    for plan in due:
        following = next_fire(plan.days, plan.times, now)
        claimed = session.execute(
            update(AutoPlan)
            .where(AutoPlan.id == plan.id, AutoPlan.next_run_at == plan.next_run_at)
            .values(next_run_at=following)).rowcount
        session.commit()
        if not claimed:
            continue                       # another process took it
        session.refresh(plan)
        try:
            fired.append(fire(session, plan, "schedule", None).id)
        except Exception:                  # noqa: BLE001
            log.exception("otomasyon planı çalıştırılamadı: %s", plan.id)
            session.rollback()
    return fired


_thread: threading.Thread | None = None


def start() -> None:
    """The scheduler thread, started with the API."""
    global _thread
    if _thread is not None or not get_settings().autotest_scheduler_enabled:
        return

    def loop():
        from ..db import SessionLocal
        while True:
            try:
                with SessionLocal() as session:
                    tick(session)
            except Exception:              # noqa: BLE001
                log.exception("otomasyon zamanlayıcısı")
            time.sleep(TICK_SECONDS)

    _thread = threading.Thread(target=loop, name="autotest-scheduler", daemon=True)
    _thread.start()
