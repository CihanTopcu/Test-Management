"""Dump a full TestRail instance to data/raw as JSON. Resumable: any file
already on disk is skipped, so re-running only fetches what is missing.

Usage: python migration/dump.py [meta|structure|execution|all] [--projects 3,8]
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testrail_client import TestRail, TestRailError

RAW = os.path.join("data", "raw")

# the per-case phases issue ~64k requests each; tune here if the
# TestRail instance feels slow for the team while a dump is running
WORKERS = int(os.environ.get("DUMP_WORKERS", "10"))
RATE_INTERVAL = float(os.environ.get("DUMP_INTERVAL", "0.08"))

# Turkish project/suite names break the default Windows console codepage.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def save(rel, obj):
    path = os.path.join(RAW, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def have(rel):
    return os.path.exists(os.path.join(RAW, rel))


def load(rel):
    with open(os.path.join(RAW, rel), encoding="utf-8") as f:
        return json.load(f)


def cached(rel, fetch):
    """Fetch unless already dumped."""
    if have(rel):
        return load(rel), True
    obj = fetch()
    save(rel, obj)
    return obj, False


def dump_meta(t):
    log("=== PHASE: meta (instance-wide configuration) ===")
    simple = {
        "users": ("get_users", "users"),
        "roles": ("get_roles", "roles"),
        "groups": ("get_groups", "groups"),
        "case_fields": ("get_case_fields", None),
        "result_fields": ("get_result_fields", None),
        "case_types": ("get_case_types", None),
        "priorities": ("get_priorities", None),
        "statuses": ("get_statuses", None),
        "projects": ("get_projects", "projects"),
    }
    for name, (path, key) in simple.items():
        data, hit = cached(f"meta/{name}.json",
                           lambda p=path, k=key: t.all(p, k) if k else t.get(p))
        log(f"  meta/{name:<14} n={len(data):<5} {'(cache)' if hit else ''}")
    return load("meta/projects.json")


def dump_structure(t, projects):
    log("=== PHASE: structure (suites / sections / cases) ===")
    total = {"suites": 0, "sections": 0, "cases": 0}
    summary = {}
    for p in projects:
        pid, pname = p["id"], p["name"]
        t0 = time.time()
        # per-project lookups that depend on the project
        for name, path, key in (("templates", f"get_templates/{pid}", None),
                                ("configs", f"get_configs/{pid}", None),
                                ("shared_steps", f"get_shared_steps/{pid}", "shared_steps")):
            try:
                cached(f"projects/{pid}/{name}.json",
                       lambda pa=path, k=key: t.all(pa, k) if k else t.get(pa))
            except TestRailError as e:
                log(f"  p{pid} {name}: SKIP ({e.code})")

        suites, _ = cached(f"projects/{pid}/suites.json",
                           lambda: t.all(f"get_suites/{pid}", "suites"))
        nsec = ncase = 0
        detail = []
        for s in suites:
            sid = s["id"]
            secs, _ = cached(f"projects/{pid}/suite_{sid}/sections.json",
                             lambda: t.all(f"get_sections/{pid}&suite_id={sid}", "sections"))
            cases, _ = cached(f"projects/{pid}/suite_{sid}/cases.json",
                              lambda: t.all(f"get_cases/{pid}&suite_id={sid}", "cases"))
            nsec += len(secs)
            ncase += len(cases)
            detail.append({"id": sid, "name": s["name"],
                           "sections": len(secs), "cases": len(cases)})
            log(f"  p{pid:<3} suite {sid:<5} {s['name'][:34]:<34} "
                f"sections={len(secs):<5} cases={len(cases):<6}")
        summary[pid] = {"name": pname, "suites": detail,
                        "n_suites": len(suites), "sections": nsec, "cases": ncase}
        total["suites"] += len(suites)
        total["sections"] += nsec
        total["cases"] += ncase
        log(f"  p{pid:<3} {pname[:30]:<30} DONE suites={len(suites):<3} "
            f"sections={nsec:<5} cases={ncase:<6} ({time.time()-t0:.0f}s, "
            f"{t.calls} calls so far)")
        save("summary_structure.json", {"projects": summary, "total": total})
    log(f"STRUCTURE TOTAL: {total}")
    return summary


def parallel(items, fn, workers=5, label="", every=200):
    """Run fn over items with a small pool; log progress periodically."""
    done = [0]
    out = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for res in ex.map(fn, items):
            out.append(res)
            done[0] += 1
            if done[0] % every == 0:
                log(f"    {label} {done[0]}/{len(items)}")
    return out


def iter_cases():
    """Yield (project_id, suite_id, case) for everything dumped by `structure`."""
    root = os.path.join(RAW, "projects")
    for pid in sorted(os.listdir(root), key=lambda x: int(x) if x.isdigit() else 0):
        pdir = os.path.join(root, pid)
        if not os.path.isdir(pdir):
            continue
        for sub in sorted(os.listdir(pdir)):
            if not sub.startswith("suite_"):
                continue
            rel = f"projects/{pid}/{sub}/cases.json"
            if have(rel):
                sid = int(sub.split("_")[1])
                for c in load(rel):
                    yield int(pid), sid, c


def dump_execution(t, projects):
    log("=== PHASE: execution (milestones / plans / runs / tests / results) ===")
    grand = {"milestones": 0, "plans": 0, "runs": 0, "tests": 0, "results": 0}
    for p in projects:
        pid, pname = p["id"], p["name"]
        t0 = time.time()
        ms, _ = cached(f"projects/{pid}/milestones.json",
                       lambda: t.all(f"get_milestones/{pid}", "milestones"))
        # milestone detail carries sub-milestones and linked runs
        for m in ms:
            cached(f"projects/{pid}/milestone_{m['id']}.json",
                   lambda mid=m["id"]: t.get(f"get_milestone/{mid}"))

        plans, _ = cached(f"projects/{pid}/plans.json",
                          lambda: t.all(f"get_plans/{pid}", "plans"))
        run_ids = []
        for pl in plans:
            detail, _ = cached(f"projects/{pid}/plan_{pl['id']}.json",
                               lambda plid=pl["id"]: t.get(f"get_plan/{plid}"))
            for entry in detail.get("entries", []):
                run_ids += [r["id"] for r in entry.get("runs", [])]

        runs, _ = cached(f"projects/{pid}/runs.json",
                         lambda: t.all(f"get_runs/{pid}", "runs"))
        run_ids += [r["id"] for r in runs]
        run_ids = sorted(set(run_ids))

        counts = {"tests": 0, "results": 0}

        def one_run(rid):
            tests, _ = cached(f"projects/{pid}/run_{rid}/tests.json",
                              lambda: t.all(f"get_tests/{rid}", "tests"))
            res, _ = cached(f"projects/{pid}/run_{rid}/results.json",
                            lambda: t.all(f"get_results_for_run/{rid}", "results"))
            return len(tests), len(res)

        for nt, nr in parallel(run_ids, one_run, workers=5,
                               label=f"p{pid} runs", every=100):
            counts["tests"] += nt
            counts["results"] += nr

        grand["milestones"] += len(ms)
        grand["plans"] += len(plans)
        grand["runs"] += len(run_ids)
        grand["tests"] += counts["tests"]
        grand["results"] += counts["results"]
        log(f"  p{pid:<3} {pname[:28]:<28} milestones={len(ms):<4} plans={len(plans):<3} "
            f"runs={len(run_ids):<5} tests={counts['tests']:<7} results={counts['results']:<7} "
            f"({time.time()-t0:.0f}s)")
        save("summary_execution.json", grand)
    log(f"EXECUTION TOTAL: {grand}")


ATTACH_RE = re.compile(r"index\.php\?/attachments/get/([0-9a-zA-Z\-]+)")


def dump_attachments(t):
    log("=== PHASE: attachments ===")
    cases = [(pid, sid, c["id"]) for pid, sid, c in iter_cases()]
    log(f"  listing attachments for {len(cases)} cases")

    def one_case(item):
        pid, sid, cid = item
        try:
            lst, _ = cached(f"attachments/case_{cid}.json",
                            lambda: t.all(f"get_attachments_for_case/{cid}", "attachments"))
            return len(lst)
        except TestRailError as e:
            return 0

    n = sum(parallel(cases, one_case, workers=WORKERS, label="  case attach", every=2000))
    log(f"  case attachment records: {n}")

    dump_inline()


def dump_inline():
    """Scan the dump for images pasted into rich-text fields.

    Purely local, no API calls. These ids never show up in any attachment
    listing, so this is the only way to find them.
    """
    log("=== PHASE: inline attachment references ===")
    inline = set()
    for dirpath, _, files in os.walk(RAW):
        for fn in files:
            if fn.endswith(".json") and fn != "attachments_inline_ids.json":
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    inline.update(ATTACH_RE.findall(f.read()))
    log(f"  inline attachment references found: {len(inline)}")
    save("attachments_inline_ids.json", sorted(inline))


def dump_history(t):
    """Fetch the change log for every case that has one.

    A case whose created_on equals its updated_on has never been edited, and
    TestRail returns an empty history for it -- verified on a sample of 15,
    all zero. Skipping those saves about 14k of 64k requests against an
    instance that rate-limits at roughly three per second.
    """
    log("=== PHASE: case history ===")
    all_cases = [c for _, _, c in iter_cases()]
    cases = [c["id"] for c in all_cases
             if c.get("created_on") != c.get("updated_on")]
    skipped = len(all_cases) - len(cases)
    log(f"  fetching history for {len(cases)} cases "
        f"({skipped} never edited, skipped)")

    def one(cid):
        try:
            h, _ = cached(f"history/case_{cid}.json",
                          lambda: t.all(f"get_history_for_case/{cid}", "history"))
            return len(h)
        except TestRailError:
            return 0

    n = sum(parallel(cases, one, workers=WORKERS, label="  history", every=2000))
    log(f"  history entries: {n}")



def dump_archived(t, projects):
    """Runs and plans TestRail keeps out of its own listings.

    get_runs returns nothing for an archived run, but the undocumented
    &is_archived=1 filter lists them, and every other endpoint works on them
    normally. Without this phase the migration quietly stops at whatever was
    still un-archived.
    """
    log("=== PHASE: archived runs and plans ===")
    grand = {"plans": 0, "runs": 0, "tests": 0, "results": 0}

    for p in projects:
        pid, pname = p["id"], p["name"]
        t0 = time.time()

        plans, _ = cached(f"projects/{pid}/plans_archived.json",
                          lambda: t.all(f"get_plans/{pid}&is_archived=1", "plans"))
        for pl in plans:
            cached(f"projects/{pid}/plan_{pl['id']}.json",
                   lambda plid=pl["id"]: t.get(f"get_plan/{plid}"))

        runs, _ = cached(f"projects/{pid}/runs_archived.json",
                         lambda: t.all(f"get_runs/{pid}&is_archived=1", "runs"))
        run_ids = [r["id"] for r in runs]
        # plan entries carry their own runs, which the run listing omits
        for pl in plans:
            key = f"projects/{pid}/plan_{pl['id']}.json"
            detail = load(key) if have(key) else {}
            for entry in detail.get("entries", []):
                run_ids += [r["id"] for r in entry.get("runs", [])]
        run_ids = sorted(set(run_ids))

        counts = {"tests": 0, "results": 0}

        def one_run(rid):
            tests, _ = cached(f"projects/{pid}/run_{rid}/tests.json",
                              lambda: t.all(f"get_tests/{rid}", "tests"))
            res, _ = cached(f"projects/{pid}/run_{rid}/results.json",
                            lambda: t.all(f"get_results_for_run/{rid}", "results"))
            return len(tests), len(res)

        for nt, nr in parallel(run_ids, one_run, workers=WORKERS,
                               label=f"p{pid} archived", every=200):
            counts["tests"] += nt
            counts["results"] += nr

        grand["plans"] += len(plans)
        grand["runs"] += len(run_ids)
        grand["tests"] += counts["tests"]
        grand["results"] += counts["results"]
        log(f"  p{pid:<3} {pname[:28]:<28} plans={len(plans):<4} runs={len(run_ids):<6} "
            f"tests={counts['tests']:<8} results={counts['results']:<8} "
            f"({time.time()-t0:.0f}s)")
        save("summary_archived.json", grand)
    log(f"ARCHIVED TOTAL: {grand}")



def dump_deleted_cases(t, projects):
    """Cases TestRail keeps out of get_cases because somebody deleted them.

    They are still referenced by the tests inside archived runs, so leaving
    them out would mean importing execution history that points at nothing.
    """
    log("=== PHASE: deleted cases ===")
    total = 0
    for p in projects:
        pid, pname = p["id"], p["name"]
        found = 0
        suites = load(f"projects/{pid}/suites.json") \
            if have(f"projects/{pid}/suites.json") else []
        for suite in suites:
            sid = suite["id"]
            rows, _ = cached(
                f"projects/{pid}/suite_{sid}/cases_deleted.json",
                lambda s=sid: t.all(
                    f"get_cases/{pid}&suite_id={s}&is_deleted=1", "cases"))
            found += len(rows)
        total += found
        if found:
            log(f"  p{pid:<3} {pname[:30]:<32} {found} silinmis case")
    log(f"DELETED TOTAL: {total}")


def main():
    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    only = None
    if "--projects" in sys.argv:
        only = {int(x) for x in sys.argv[sys.argv.index("--projects") + 1].split(",")}

    t = TestRail(min_interval=RATE_INTERVAL)
    start = time.time()
    projects = dump_meta(t)
    if only:
        projects = [p for p in projects if p["id"] in only]

    if phase in ("structure", "all"):
        dump_structure(t, projects)
    if phase in ("execution", "all"):
        dump_execution(t, projects)
    if phase in ("archived", "all"):
        dump_archived(t, projects)
    if phase in ("deleted", "all"):
        dump_deleted_cases(t, projects)
    if phase in ("inline", "attachments", "all"):
        dump_inline()
    if phase in ("attachments", "all"):
        dump_attachments(t)
    if phase in ("history", "all"):
        dump_history(t)

    log(f"finished in {time.time()-start:.0f}s, {t.calls} API calls, "
        f"{t.throttled} throttle waits")


if __name__ == "__main__":
    main()
