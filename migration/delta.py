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


def dump_delta(t: TestRail, since: int, only: int | None = None) -> dict:
    """Refresh the dump for everything TestRail says changed since `since`.

    Writes into the same layout dump.py produces, overwriting the files it
    touches, so load.py picks the changes up without a second code path.

    Returns a manifest naming exactly which suites and runs were rewritten,
    so the load step can touch those and leave the other 13,000 run
    directories alone.
    """
    projects = json.load(open(os.path.join(RAW, "meta", "projects.json"),
                              encoding="utf-8"))
    if only:
        projects = [p for p in projects if p["id"] == only]

    manifest = {"suites": [], "runs": [], "projects": [], "changed_cases": [],
                "cases": 0, "runs_touched": 0, "results": 0, "milestones": 0,
                "history": 0}

    for p in projects:
        pid, pname = p["id"], p["name"]
        touched_here = False

        # --- cases: ask each suite whether anything moved ------------------
        suites = t.all(f"get_suites/{pid}", "suites")
        save(f"projects/{pid}/suites.json", suites)
        for suite in suites:
            sid = suite["id"]
            changed = t.all(
                f"get_cases/{pid}&suite_id={sid}&updated_after={since}", "cases")
            if not changed:
                continue
            # one changed case means the suite file is stale; re-fetch it
            # whole rather than splicing rows into a JSON array
            save(f"projects/{pid}/suite_{sid}/cases.json",
                 t.all(f"get_cases/{pid}&suite_id={sid}", "cases"))
            save(f"projects/{pid}/suite_{sid}/sections.json",
                 t.all(f"get_sections/{pid}&suite_id={sid}", "sections"))
            manifest["suites"].append(sid)
            manifest["cases"] += len(changed)
            touched_here = True

            # Who changed what. Without this the case arrives with its new
            # values and no record of the edit, which is the one thing the
            # activity report cannot reconstruct afterwards.
            for case in changed:
                cid = case["id"]
                entries = t.all(f"get_history_for_case/{cid}", "history")
                save(f"history/case_{cid}.json", entries)
                manifest["changed_cases"].append(cid)
                manifest["history"] += len(entries)

        # --- milestones and plans: small, always refreshed -----------------
        milestones = t.all(f"get_milestones/{pid}", "milestones")
        save(f"projects/{pid}/milestones.json", milestones)
        for m in milestones:
            save(f"projects/{pid}/milestone_{m['id']}.json",
                 t.get(f"get_milestone/{m['id']}"))
        manifest["milestones"] += len(milestones)

        plans = t.all(f"get_plans/{pid}", "plans")
        save(f"projects/{pid}/plans.json", plans)
        plan_runs = []
        for plan in plans:
            detail = t.get(f"get_plan/{plan['id']}")
            save(f"projects/{pid}/plan_{plan['id']}.json", detail)
            for entry in detail.get("entries") or []:
                plan_runs += entry.get("runs") or []

        # --- runs ----------------------------------------------------------
        runs = t.all(f"get_runs/{pid}", "runs")
        save(f"projects/{pid}/runs.json", runs)
        # get_runs leaves out the runs inside a test plan; without these a
        # result entered in a plan never reached us
        runs = runs + plan_runs
        known = set(runs_on_disk(pid))

        for run in runs:
            rid = run["id"]
            fresh = rid not in known
            if fresh:
                new_results = None          # a new run: take everything
            else:
                # An archived run is read-only in TestRail, so it cannot have
                # gained anything; skipping those is what keeps a weekly pass
                # to minutes instead of hours.
                if run.get("is_archived"):
                    continue
                new_results = t.all(
                    f"get_results_for_run/{rid}&created_after={since}",
                    "results")
                if not new_results:
                    continue

            tests = t.all(f"get_tests/{rid}", "tests")
            results = t.all(f"get_results_for_run/{rid}", "results")
            save(f"projects/{pid}/run_{rid}/tests.json", tests)
            save(f"projects/{pid}/run_{rid}/results.json", results)
            manifest["runs"].append(rid)
            manifest["runs_touched"] += 1
            manifest["results"] += len(new_results) if new_results else len(results)
            touched_here = True

        if touched_here:
            manifest["projects"].append(pid)
            log(f"  {pname[:30]:<32} suite={len([x for x in manifest['suites']]):<4} "
                f"kosum={manifest['runs_touched']:<5} sonuc={manifest['results']}")

    manifest["since"] = since
    manifest["taken_at"] = datetime.now(timezone.utc).isoformat()
    save("delta/manifest.json", manifest)
    log(f"DELTA: case={manifest['cases']} kosum={manifest['runs_touched']} "
        f"sonuc={manifest['results']} gecmis={manifest['history']}")
    return manifest


def runs_on_disk(pid: int) -> list[int]:
    """Run directories already in the dump, so new ones can be spotted."""
    pdir = os.path.join(RAW, "projects", str(pid))
    if not os.path.isdir(pdir):
        return []
    return [int(d.split("_")[1]) for d in os.listdir(pdir)
            if d.startswith("run_")]


def load_delta(manifest: dict | None = None) -> dict:
    """Load exactly what the delta touched.

    The full loader walks 13,929 run directories and upserts 1.09M results,
    which took the best part of an hour on the initial import. A weekly sync
    that only changed four runs has no business doing that, so the phases
    are handed the manifest and skip everything else.
    """
    if manifest is None:
        with open(os.path.join(RAW, "delta", "manifest.json"),
                  encoding="utf-8") as f:
            manifest = json.load(f)

    import load as loader

    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    from sqlalchemy.orm import Session as _Session

    with _Session(engine) as session:
        # access is administered here now: the sync may add a new account or
        # membership, but it no longer overwrites or deletes one
        loader.load_catalog(session, initial=False)
        loader.load_custom_fields(session)
        loader.load_projects(session, initial=False)
        loader.load_milestones(session)
        structure = loader.load_structure(
            session, only_suites=set(manifest.get("suites") or []))
        execution = loader.load_execution(
            session, only_runs=set(manifest.get("runs") or []))
        # after the cases exist, so history has something to attach to
        loader.load_history(
            session, only_cases=set(manifest.get("changed_cases") or []))
        loader.fix_sequences(session)

    return {"loaded_cases": structure.get("cases", 0),
            "loaded_tests": execution.get("tests", 0),
            "loaded_results": execution.get("results", 0),
            "loaded_history": manifest.get("history", 0)}


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
