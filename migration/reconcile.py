"""Compare our copy with live TestRail, entity by entity.

verify.py checks the database against the dump taken at migration time;
this asks TestRail itself, so it also catches whatever the sync has missed
since. Read-only on both sides.

    python migration/reconcile.py                 # every project
    python migration/reconcile.py --project 3     # one project
    python migration/reconcile.py --deep 50       # dig into 50 runs that disagree

Tests and results are not fetched one by one -- that would be a million
requests. Every TestRail run carries per-status counts of its tests; those
are compared with ours, and only runs that disagree are opened (--deep) to
say which tests and results are missing.

The report lands in data/reconcile/<time>.json.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402
from testrail_client import TestRail, TestRailError  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

WORKERS = 4
# every run TestRail lists (i.e. not archived) that we also hold; --all-results
# opens each of them, since equal status counts can still hide a second
# result with the same status
LISTED = []
# status id -> the field TestRail counts it in on a run
COUNT_FIELD = {1: "passed_count", 2: "blocked_count", 3: "untested_count",
               4: "retest_count", 5: "failed_count"}
for _n in range(1, 8):
    COUNT_FIELD[5 + _n] = f"custom_status{_n}_count"


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def ts(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc) if epoch else None


def pmap(fn, items):
    with ThreadPoolExecutor(WORKERS) as pool:
        return list(pool.map(fn, items))


class Diff:
    """Missing here, extra here (gone from TestRail) and stale, per entity."""

    def __init__(self):
        self.rows = defaultdict(lambda: {"testrail": 0, "local": 0, "missing": [],
                                         "extra": [], "stale": []})

    def ids(self, entity, live, local):
        d = self.rows[entity]
        d["testrail"] += len(live)
        d["local"] += len(local)
        d["missing"] += sorted(set(live) - set(local))
        d["extra"] += sorted(set(local) - set(live))
        return d

    def stale(self, entity, item):
        self.rows[entity]["stale"].append(item)

    def explain_extra(self, t, entity, local, probe):
        """TestRail's lists leave archived runs and plans out, so "we have it,
        TestRail does not list it" is usually just the archive. A completed
        one is taken as archived (TestRail only archives completed ones);
        an open one is asked for by id: archived, or really deleted?"""
        d = self.rows[entity]
        keep = []
        for i in d["extra"]:
            if i not in local:
                keep.append(i)
                continue
            if local[i][0]:
                d["archived"] = d.get("archived", 0) + 1
                continue
            try:
                item = t.get(f"{probe}/{i}", retries=2)
                if item.get("is_archived"):
                    d["archived"] = d.get("archived", 0) + 1
                    d.setdefault("archived_but_open_here", []).append(i)
                else:
                    keep.append(i)
            except TestRailError as e:
                if e.code == 400:
                    d.setdefault("deleted_in_testrail", []).append(i)
                else:
                    keep.append(i)
        d["extra"] = keep


# --- the local side ----------------------------------------------------------

def local_ids(c, sql, **kw):
    return {r[0]: r[1:] for r in c.execute(text(sql), kw)}


def milestone_ids(items):
    """get_milestones nests sub-milestones; flatten them."""
    out = {}
    for m in items:
        out[m["id"]] = m
        out.update(milestone_ids(m.get("milestones") or []))
    return out


def reconcile_project(t, c, p, diff, run_status):
    pid = p["id"]
    local_pid = c.execute(text("SELECT id FROM projects WHERE testrail_id=:p"),
                          {"p": pid}).scalar()
    if local_pid is None:
        log(f"  {p['name']}: bizde yok")
        return []
    out_runs = []

    # suites, sections, cases -------------------------------------------------
    suites = t.all(f"get_suites/{pid}", "suites")
    diff.ids("suites", [s["id"] for s in suites], local_ids(c,
             "SELECT testrail_id FROM suites WHERE project_id=:p AND testrail_id IS NOT NULL",
             p=local_pid))

    def per_suite(s):
        sid = s["id"]
        return (t.all(f"get_sections/{pid}&suite_id={sid}", "sections"),
                t.all(f"get_cases/{pid}&suite_id={sid}", "cases"))

    fetched = pmap(per_suite, suites)
    sections = [x for secs, _ in fetched for x in secs]
    cases = [x for _, cs in fetched for x in cs]

    diff.ids("sections", [s["id"] for s in sections], local_ids(c,
             "SELECT x.testrail_id FROM sections x JOIN suites s ON s.id=x.suite_id "
             "WHERE s.project_id=:p AND x.testrail_id IS NOT NULL AND NOT x.is_deleted",
             p=local_pid))

    ours = local_ids(c,
                     "SELECT x.testrail_id, x.updated_on, x.title FROM cases x "
                     "JOIN suites s ON s.id=x.suite_id WHERE s.project_id=:p "
                     "AND x.testrail_id IS NOT NULL AND NOT x.is_deleted",
                     p=local_pid)
    diff.ids("cases", [x["id"] for x in cases], ours)
    for x in cases:
        mine = ours.get(x["id"])
        if not mine:
            continue
        live_upd = ts(x.get("updated_on"))
        if live_upd and (mine[0] is None or live_upd > mine[0]):
            diff.stale("cases", {"id": x["id"], "title": x["title"],
                                 "testrail_updated": live_upd.isoformat(),
                                 "local_updated": mine[0].isoformat() if mine[0] else None,
                                 "project": p["name"]})

    # milestones --------------------------------------------------------------
    ms = milestone_ids(t.all(f"get_milestones/{pid}", "milestones"))
    ours = local_ids(c, "SELECT testrail_id, is_completed FROM milestones "
                        "WHERE project_id=:p AND testrail_id IS NOT NULL", p=local_pid)
    diff.ids("milestones", ms, ours)
    for mid, m in ms.items():
        if mid in ours and bool(m.get("is_completed")) != ours[mid][0]:
            diff.stale("milestones", {"id": mid, "name": m["name"], "project": p["name"],
                                      "field": "is_completed",
                                      "testrail": m.get("is_completed"), "local": ours[mid][0]})

    # plans and their runs ----------------------------------------------------
    plans = t.all(f"get_plans/{pid}", "plans")
    ours = local_ids(c, "SELECT testrail_id, is_completed FROM plans "
                        "WHERE project_id=:p AND testrail_id IS NOT NULL", p=local_pid)
    diff.ids("plans", [x["id"] for x in plans], ours)
    diff.explain_extra(t, "plans", ours, "get_plan")
    for x in plans:
        if x["id"] in ours and bool(x.get("is_completed")) != ours[x["id"]][0]:
            diff.stale("plans", {"id": x["id"], "name": x["name"], "project": p["name"],
                                 "field": "is_completed",
                                 "testrail": x.get("is_completed"), "local": ours[x["id"]][0]})

    runs = [dict(r, _plan=None) for r in t.all(f"get_runs/{pid}", "runs")]
    for plan in pmap(lambda x: t.get(f"get_plan/{x['id']}"), plans):
        for entry in plan.get("entries") or []:
            for r in entry.get("runs") or []:
                runs.append(dict(r, _plan=plan["id"]))

    ours = local_ids(c, "SELECT testrail_id, is_completed, id FROM runs "
                        "WHERE project_id=:p AND testrail_id IS NOT NULL", p=local_pid)
    d = diff.ids("runs", [r["id"] for r in runs], ours)
    in_plan = {r["id"] for r in runs if r["_plan"]}
    d.setdefault("missing_in_plans", 0)
    d["missing_in_plans"] += len([r for r in d["missing"] if r in in_plan])
    diff.explain_extra(t, "runs", ours, "get_run")

    for r in runs:
        rid = r["id"]
        if rid not in ours:
            continue
        LISTED.append({"id": rid, "local_id": ours[rid][1], "name": r["name"],
                       "project": p["name"], "in_plan": bool(r["_plan"])})
        if bool(r.get("is_completed")) != ours[rid][0]:
            diff.stale("runs", {"id": rid, "name": r["name"], "project": p["name"],
                                "field": "is_completed",
                                "testrail": r.get("is_completed"), "local": ours[rid][0]})
        live = {s: r.get(f, 0) or 0 for s, f in COUNT_FIELD.items()}
        mine = run_status.get(ours[rid][1], Counter())
        if any(live[s] != mine.get(s, 0) for s in COUNT_FIELD):
            out_runs.append({
                "id": rid, "local_id": ours[rid][1], "name": r["name"],
                "project": p["name"], "in_plan": bool(r["_plan"]),
                "is_completed": bool(r.get("is_completed")),
                "testrail": {s: n for s, n in live.items() if n},
                "local": {s: n for s, n in mine.items() if n},
            })

    log(f"  {p['name'][:32]:<34} case {len(cases):>6}  kosum {len(runs):>5}  "
        f"durumu tutmayan kosum {len(out_runs)}")
    return out_runs


def dig(t, c, run):
    """For a run whose counts disagree: which tests and results differ."""
    tests = t.all(f"get_tests/{run['id']}", "tests")
    results = t.all(f"get_results_for_run/{run['id']}", "results")
    our_tests = local_ids(c, "SELECT testrail_id, status_id FROM tests "
                             "WHERE run_id=:r AND testrail_id IS NOT NULL", r=run["local_id"])
    our_results = local_ids(c, "SELECT r.testrail_id, r.status_id FROM results r "
                               "JOIN tests x ON x.id=r.test_id "
                               "WHERE x.run_id=:r AND r.testrail_id IS NOT NULL",
                            r=run["local_id"])
    live_tests = {x["id"]: x for x in tests}
    run["tests_missing"] = sorted(set(live_tests) - set(our_tests))
    run["tests_extra"] = sorted(set(our_tests) - set(live_tests))
    run["tests_status_differs"] = sorted(
        i for i, x in live_tests.items()
        if i in our_tests and x.get("status_id") != our_tests[i][0])
    live_results = {x["id"]: x for x in results}
    missing = sorted(set(live_results) - set(our_results))
    run["results_missing"] = len(missing)
    run["results_extra"] = len(set(our_results) - set(live_results))
    if missing:
        newest = max(live_results[i]["created_on"] for i in missing)
        oldest = min(live_results[i]["created_on"] for i in missing)
        run["results_missing_span"] = [ts(oldest).isoformat(), ts(newest).isoformat()]
    return run


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", type=int)
    ap.add_argument("--deep", type=int, default=40,
                    help="how many disagreeing runs to open (0: none)")
    ap.add_argument("--all-results", action="store_true",
                    help="compare result ids in every run TestRail lists")
    args = ap.parse_args()

    t = TestRail(min_interval=0.1)
    engine = create_engine(get_settings().database_url, future=True)
    diff = Diff()
    started = datetime.now()

    # autocommit: a read-only pass of half an hour must not hold a transaction
    # open, or the API cannot start (its start-up waits for table locks)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
        projects = t.all("get_projects", "projects")
        ours = local_ids(c, "SELECT testrail_id, name FROM projects WHERE testrail_id IS NOT NULL")
        diff.ids("projects", [p["id"] for p in projects], ours)

        users = t.all("get_users", "users")
        ours_u = local_ids(c, "SELECT testrail_id, email, is_active FROM users "
                              "WHERE testrail_id IS NOT NULL")
        diff.ids("users", [u["id"] for u in users], ours_u)
        for u in users:
            if u["id"] in ours_u and bool(u.get("is_active")) != ours_u[u["id"]][1]:
                diff.stale("users", {"id": u["id"], "email": u.get("email"),
                                     "field": "is_active",
                                     "testrail": u.get("is_active"), "local": ours_u[u["id"]][1]})

        log("yerel test durumlari okunuyor")
        run_status = defaultdict(Counter)
        for run_id, status, n in c.execute(text(
                "SELECT run_id, coalesce(status_id, 3), count(*) FROM tests "
                "WHERE testrail_id IS NOT NULL GROUP BY 1, 2")):
            run_status[run_id][status] = n

        if args.project:
            projects = [p for p in projects if p["id"] == args.project]
        disagreeing = []
        for p in projects:
            try:
                disagreeing += reconcile_project(t, c, p, diff, run_status)
            except TestRailError as e:
                log(f"  {p['name']}: {e}")

        # newest first: those are the ones the sync is expected to have
        disagreeing.sort(key=lambda r: r["id"], reverse=True)
        if args.deep:
            log(f"{min(args.deep, len(disagreeing))} kosum ayrintili inceleniyor")
            for run in disagreeing[:args.deep]:
                dig(t, c, run)
        if args.all_results:
            log(f"{len(LISTED)} kosumun sonuclari tek tek karsilastiriliyor")
            for n, run in enumerate(LISTED, 1):
                dig(t, c, run)
                if n % 100 == 0:
                    log(f"  {n}/{len(LISTED)}")
            gaps = [r for r in LISTED if r["tests_missing"] or r["results_missing"]
                    or r["tests_status_differs"] or r["results_extra"] or r["tests_extra"]]
            disagreeing += [r for r in gaps if r not in disagreeing]

    report = {
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "seconds": round((datetime.now() - started).total_seconds()),
        "requests": t.calls,
        "entities": diff.rows,
        "runs_disagreeing": disagreeing,
    }
    os.makedirs(os.path.join("data", "reconcile"), exist_ok=True)
    path = os.path.join("data", "reconcile", f"{datetime.now():%Y%m%d-%H%M}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)

    print()
    print(f"{'':12} {'TestRail':>9} {'bizde':>9} {'eksik':>7} {'fazla':>7} "
          f"{'eski':>6} {'arsivde':>8} {'silinmis':>9}")
    for name, d in diff.rows.items():
        print(f"{name:12} {d['testrail']:>9} {d['local']:>9} {len(d['missing']):>7} "
              f"{len(d['extra']):>7} {len(d['stale']):>6} {d.get('archived', 0):>8} "
              f"{len(d.get('deleted_in_testrail', [])):>9}")
    print(f"durum sayilari tutmayan kosum: {len(disagreeing)}")
    log(f"rapor: {path}  ({t.calls} istek)")


if __name__ == "__main__":
    main()
