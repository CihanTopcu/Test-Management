"""Unattended TestRail sync for the cut-over window.

While both systems are alive, TestRail keeps being edited. This pulls what
changed and loads it, on a schedule, so the new instance never drifts more
than one interval behind. It is temporary by design: when TestRail is shut
down, set TESTRAIL_SYNC_ENABLED=false (or drop the container) and nothing
else needs unpicking.

    python migration/sync.py              # one pass, then exit
    python migration/sync.py --loop       # keep going, one pass per interval
    python migration/sync.py --status     # what the last runs did

The admin page can also ask for a pass now ("Şimdi eşitle"). It writes a
queued row and nothing else; the loop below checks for one every
TESTRAIL_SYNC_POLL seconds (default 30) while it waits out the interval,
and a one-off run takes a waiting request too.

Three things it is careful about, all of them learned the hard way:

  The window only moves forward on success. A failed run leaves it where it
  was, so the next one covers both periods rather than skipping a week.

  Every window is widened by an overlap. TestRail's updated_after is
  second-granularity, and a record written while the previous pass was
  reading could otherwise fall between two windows. Loading is an upsert, so
  re-reading a record costs nothing and missing one costs a lot.

  Deletions are invisible. TestRail's API does not report them, so a case
  deleted in TestRail stays in our copy. Every run records the count
  difference instead of pretending the two sides match.
"""
import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))
sys.path.insert(0, HERE)

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import delta  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.models import Base, Role, SyncRun, User  # noqa: E402
from app.notifications import notify  # noqa: E402
from testrail_client import TestRail  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

# Re-reading a few minutes of already-loaded records is free; missing one is
# not, so every window reaches back a little further than it strictly needs.
OVERLAP = timedelta(minutes=30)

# A pass that has not finished in this long is assumed dead -- the container
# was killed mid-run -- and no longer blocks the next one.
STALE_AFTER = timedelta(hours=8)


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


def engine_for():
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    return create_engine(url, future=True)


def enabled() -> bool:
    return os.environ.get("TESTRAIL_SYNC_ENABLED", "true").lower() not in (
        "0", "false", "no", "off")


def interval_seconds() -> int:
    """Default one week; the team decided that is often enough."""
    return int(os.environ.get("TESTRAIL_SYNC_INTERVAL", 7 * 24 * 3600))


def _bootstrap_since() -> datetime:
    """Where to start when there has never been a successful sync.

    Falls back to the moment of the original export rather than the epoch:
    asking TestRail for everything since 1970 would fetch the whole instance
    again, slowly, for nothing.
    """
    configured = os.environ.get("TESTRAIL_SYNC_SINCE")
    if configured:
        value = datetime.fromisoformat(configured.replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - timedelta(days=7)


def window_start(session: Session) -> datetime:
    last_ok = session.scalar(
        select(SyncRun).where(SyncRun.status == "ok")
        .order_by(SyncRun.finished_on.desc()).limit(1))
    if last_ok is None or last_ok.finished_on is None:
        return _bootstrap_since()
    finished = last_ok.finished_on
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=timezone.utc)
    return finished - OVERLAP


def poll_seconds() -> int:
    return int(os.environ.get("TESTRAIL_SYNC_POLL", 30))


def queued_request(session: Session) -> SyncRun | None:
    """The oldest pass someone asked for from the admin page."""
    return session.scalar(
        select(SyncRun).where(SyncRun.status == "queued")
        .order_by(SyncRun.started_on.asc()).limit(1))


def claim(session: Session, trigger: str) -> SyncRun | None:
    """Start a run, unless one is already in flight.

    A request queued from the admin page is taken over rather than a new row
    written beside it, so the history shows one manual run where somebody
    pressed the button, not a queued row that never went anywhere.
    """
    now = datetime.now(timezone.utc)
    running = session.scalar(
        select(SyncRun).where(SyncRun.status == "running")
        .order_by(SyncRun.started_on.desc()).limit(1))
    if running is not None:
        started = running.started_on
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if now - started < STALE_AFTER:
            log(f"zaten calisan bir esitleme var (#{running.id}), atlaniyor")
            return None
        log(f"onceki esitleme (#{running.id}) yarim kalmis, oluye alindi")
        running.status = "failed"
        running.error = "yarim kaldi (konteyner yeniden baslatilmis olabilir)"
        running.finished_on = now

    run = queued_request(session)
    if run is not None:
        log(f"yonetim sayfasindan istenen esitleme (#{run.id}) basliyor")
        run.status = "running"
        run.started_on = now
        run.window_from = window_start(session)
    else:
        run = SyncRun(started_on=now, status="running", trigger=trigger,
                      window_from=window_start(session))
        session.add(run)
    session.commit()
    session.refresh(run)
    return run


def tell_admins(session: Session, subject: str, body: str) -> None:
    """Failures should not wait for somebody to open the admin page."""
    admins = session.scalars(
        select(User).join(Role, User.role_id == Role.id)
        .where(Role.name == "Admin", User.is_active.is_(True))).all()
    for admin in admins:
        notify(session, admin.id, "digest", subject, body,
               link="/#/admin")
    session.commit()


def run_once(trigger: str = "schedule") -> int:
    """One pass. Returns a process exit code."""
    if not enabled():
        log("TESTRAIL_SYNC_ENABLED=false — esitleme kapali")
        return 0

    engine = engine_for()
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        run = claim(session, trigger)
        if run is None:
            return 0
        started = time.time()
        since = run.window_from
        log(f"esitleme #{run.id} basliyor, pencere: {since:%Y-%m-%d %H:%M} ->")

        try:
            # credentials come from .env the same way every migration tool
            # reads them; the gentle interval keeps us under TestRail's limit
            client = TestRail(min_interval=0.3)
            manifest = delta.dump_delta(client, int(since.timestamp()))
            loaded = delta.load_delta(manifest)
            summary = {"cases": manifest["cases"],
                       "runs": manifest["runs_touched"],
                       "results": manifest["results"],
                       "milestones": manifest["milestones"]}

            run.counts = {**summary, **loaded,
                          "seconds": round(time.time() - started)}
            run.status = "ok"
            run.finished_on = datetime.now(timezone.utc)
            session.commit()
            log(f"esitleme #{run.id} tamam: {run.counts}")

            changed = sum(summary.get(k, 0) for k in ("cases", "runs", "results"))
            if changed:
                tell_admins(
                    session, f"TestRail eşitlemesi: {changed} değişiklik",
                    f"{summary.get('cases', 0)} case, {summary.get('runs', 0)}"
                    f" koşum, {summary.get('results', 0)} sonuç alındı.")
            return 0

        except Exception as exc:                       # noqa: BLE001
            run.status = "failed"
            run.finished_on = datetime.now(timezone.utc)
            run.error = f"{type(exc).__name__}: {exc}"[:4000]
            session.commit()
            log(f"esitleme #{run.id} BASARISIZ: {run.error}")
            traceback.print_exc()
            tell_admins(
                session, "TestRail eşitlemesi başarısız",
                f"{run.error}\n\nPencere ilerletilmedi; bir sonraki deneme"
                " aynı dönemi de kapsayacak.")
            return 1


def show_status() -> int:
    engine = engine_for()
    # the table may not exist yet on an instance that has never synced
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        runs = session.scalars(
            select(SyncRun).order_by(SyncRun.started_on.desc()).limit(10)).all()
        if not runs:
            print("henuz hic esitleme calismadi")
            return 0
        print(f"{'basladi':<20} {'durum':<8} {'sure':>6}  ozet")
        print("-" * 78)
        for r in runs:
            seconds = (r.counts or {}).get("seconds", "")
            detail = r.error[:38] if r.error else ", ".join(
                f"{k}={v}" for k, v in (r.counts or {}).items()
                if k in ("cases", "runs", "results"))
            print(f"{r.started_on:%Y-%m-%d %H:%M}     {r.status:<8} "
                  f"{seconds:>6}  {detail}")
    return 0


def wait_for_next(every: int) -> None:
    """Sleep until the next scheduled pass, or until someone asks for one.

    The interval is a week, so a plain sleep would make the admin page's
    button wait up to seven days. Waking every few seconds to look for a
    queued row costs one indexed query.
    """
    deadline = time.time() + every
    engine = engine_for()
    while time.time() < deadline:
        time.sleep(min(poll_seconds(), max(0.0, deadline - time.time())))
        try:
            with Session(engine) as session:
                if queued_request(session) is not None:
                    return
        except Exception:                              # noqa: BLE001
            # the database being briefly away is not a reason to stop waiting
            traceback.print_exc()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--loop", action="store_true",
                        help="surekli calis, her aralikta bir gec")
    parser.add_argument("--status", action="store_true",
                        help="son esitlemeleri goster ve cik")
    parser.add_argument("--trigger", default="schedule",
                        choices=["schedule", "manual"])
    args = parser.parse_args()

    if args.status:
        return show_status()
    if not args.loop:
        return run_once(args.trigger)

    every = interval_seconds()
    log(f"dongu modu: her {every // 3600} saatte bir")
    while True:
        if not enabled():
            # the off switch takes effect without a redeploy
            log("esitleme kapatilmis, dongu sonlandi")
            return 0
        try:
            run_once()
        except Exception:                              # noqa: BLE001
            # a crash here must not stop the schedule; the next pass retries
            traceback.print_exc()
        wait_for_next(every)


if __name__ == "__main__":
    raise SystemExit(main())
