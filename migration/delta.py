"""Incremental sync for the cut-over window.

A full export takes hours, and TestRail keeps being used while it runs. This
fetches only what changed since a given moment, so the switch can be: freeze
TestRail, run this, verify, redirect people. Minutes rather than a weekend.

    python migration/delta.py --since 2026-09-24T08:00      # dump changes
    python migration/delta.py --since ... --load            # and load them
    python migration/delta.py --report                      # compare counts

What it can and cannot see:
  * new and edited cases  -- TestRail filters get_cases by updated_after
  * new runs and results  -- filtered by created_after
  * new milestones        -- fetched whole, they are few
  * deletions             -- NOT visible; TestRail's API does not report
    them, so a case deleted during the window stays in our copy. The
    comparison report surfaces the count difference instead of pretending.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from testrail_client import TestRail, TestRailError  # noqa: E402

RAW = os.path.join("data", "raw")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def save(rel, obj):
    path = os.path.join(RAW, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def epoch(value: str) -> int:
    text_value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def dump_delta(t: TestRail, since: int, only: int | None = None):
    projects = json.load(open(os.path.join(RAW, "meta", "projects.json"),
                              encoding="utf-8"))
    if only:
        projects = [p for p in projects if p["id"] == only]
    summary = {"cases": 0, "runs": 0, "results": 0, "milestones": 0}

    for p in projects:
        pid, pname = p["id"], p["name"]
        suites = t.all(f"get_suites/{pid}", "suites")

        changed_cases = []
        for s in suites:
            rows = t.all(
                f"get_cases/{pid}&suite_id={s['id']}&updated_after={since}",
                "cases")
            changed_cases += rows
        if changed_cases:
            save(f"delta/{pid}/cases.json", changed_cases)

        runs = t.all(f"get_runs/{pid}&created_after={since}", "runs")
        if runs:
            save(f"delta/{pid}/runs.json", runs)

        results = 0
        # results land in runs that may themselves predate the window, so
        # every run the project knows about has to be asked
        for run in t.all(f"get_runs/{pid}", "runs"):
            rows = t.all(f"get_results_for_run/{run['id']}&created_after={since}",
                         "results")
            if rows:
                save(f"delta/{pid}/results_{run['id']}.json", rows)
                results += len(rows)

        milestones = t.all(f"get_milestones/{pid}", "milestones")
        save(f"delta/{pid}/milestones.json", milestones)

        summary["cases"] += len(changed_cases)
        summary["runs"] += len(runs)
        summary["results"] += results
        summary["milestones"] += len(milestones)
        if changed_cases or runs or results:
            log(f"  {pname[:30]:<32} case={len(changed_cases):<5} "
                f"run={len(runs):<4} sonuc={results}")

    save("delta/summary.json", {**summary, "since": since,
                                "taken_at": datetime.now(timezone.utc).isoformat()})
    log(f"DELTA: {summary}")
    return summary


def report(t: TestRail):
    """Side-by-side counts, TestRail against our database.

    The one number that cannot be reconciled automatically is deletions: if
    TestRail shows fewer cases than we hold, somebody deleted them after the
    export and the difference has to be looked at by a person.
    """
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    projects = json.load(open(os.path.join(RAW, "meta", "projects.json"),
                              encoding="utf-8"))

    print(f"{'proje':<30} {'TestRail case':>14} {'bizde':>8} {'fark':>7}")
    print("-" * 64)
    total_tr = total_db = 0
    with engine.connect() as c:
        for p in projects:
            pid = p["id"]
            tr = 0
            for s in t.all(f"get_suites/{pid}", "suites"):
                tr += len(t.all(f"get_cases/{pid}&suite_id={s['id']}", "cases"))
            db = c.execute(text(
                "select count(*) from cases k join suites s on s.id = k.suite_id "
                "where s.project_id = :p and k.is_deleted = false"),
                {"p": pid}).scalar()
            total_tr += tr
            total_db += db
            diff = tr - db
            mark = "" if diff == 0 else ("  <-- FARK" if diff else "")
            print(f"{p['name'][:29]:<30} {tr:>14,} {db:>8,} {diff:>7,}{mark}"
                  .replace(",", "."))
    print("-" * 64)
    print(f"{'TOPLAM':<30} {total_tr:>14,} {total_db:>8,} "
          f"{total_tr - total_db:>7,}".replace(",", "."))
    if total_tr != total_db:
        print("\nFark sifir degil. Pozitif fark: TestRail'de yeni kayit var, "
              "delta calistirin.\nNegatif fark: TestRail'de silinmis kayitlar "
              "var, elle incelenmeli.")
    return total_tr - total_db


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", help="ISO tarih, orn. 2026-09-24T08:00")
    ap.add_argument("--load", action="store_true",
                    help="delta'yi cektikten sonra veritabanina yukle")
    ap.add_argument("--report", action="store_true",
                    help="TestRail ile veritabanini sayim olarak karsilastir")
    ap.add_argument("--project", type=int,
                    help="yalnizca bu proje (deneme icin)")
    args = ap.parse_args()

    t = TestRail(min_interval=0.3)

    if args.report:
        sys.exit(1 if report(t) else 0)

    if not args.since:
        ap.error("--since veya --report gerekli")

    since = epoch(args.since)
    log(f"{args.since} tarihinden beri degisenler cekiliyor (epoch {since})")
    dump_delta(t, since, args.project)

    if args.load:
        log("veritabanina yukleniyor…")
        # the normal loader is idempotent, so re-running it over the full dump
        # picks the delta up without a second code path to keep correct
        subprocess.run([sys.executable, "migration/load.py", "all"], check=True)


if __name__ == "__main__":
    main()
