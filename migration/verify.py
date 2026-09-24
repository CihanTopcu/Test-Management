"""Reconcile the loaded database against the raw TestRail dump.

Counting rows proves nothing on its own -- a loader that silently drops a
field still produces the right number of rows. So this does two passes:

1. counts, per project, for every entity;
2. a field-by-field comparison of randomly sampled cases and results,
   including custom fields and steps.

Exits non-zero if anything disagrees, so it can gate the cut-over.
"""
import glob
import json
import os
import random
import sys

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app import models  # noqa: E402

RAW = os.path.join("data", "raw")
SAMPLE = int(os.environ.get("VERIFY_SAMPLE", "300"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

problems = []


def log(msg):
    print(msg, flush=True)


def fail(msg):
    problems.append(msg)
    log(f"  !! {msg}")


def read(rel, default=None):
    path = os.path.join(RAW, rel)
    if not os.path.exists(path):
        return default if default is not None else []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def project_ids():
    root = os.path.join(RAW, "projects")
    return sorted(int(d) for d in os.listdir(root) if d.isdigit())


# results the dump holds but nothing can own: get_results_for_run returns
# results for tests that were removed from the run afterwards
ORPHANS = {}


def raw_counts():
    """Everything the dump says exists, per project.

    Counted the way the loader loads it, so a difference means a real loss:
    soft-deleted cases are included (they are rows here too) and results
    whose test is not in the same run are excluded (nothing can own them).
    """
    out = {}
    for pid in project_ids():
        base = os.path.join(RAW, "projects", str(pid))
        suites = read(f"projects/{pid}/suites.json")
        sections = cases = tests = results = orphans = 0
        for d in os.listdir(base):
            if d.startswith("suite_"):
                sections += len(read(f"projects/{pid}/{d}/sections.json"))
                cases += len(read(f"projects/{pid}/{d}/cases.json"))
                cases += len(read(f"projects/{pid}/{d}/cases_deleted.json"))
            elif d.startswith("run_"):
                run_tests = read(f"projects/{pid}/{d}/tests.json")
                known = {t["id"] for t in run_tests}
                run_results = read(f"projects/{pid}/{d}/results.json")
                loadable = [r for r in run_results if r.get("test_id") in known]
                tests += len(run_tests)
                results += len(loadable)
                orphans += len(run_results) - len(loadable)
        runs = len([d for d in os.listdir(base) if d.startswith("run_")])
        ORPHANS[pid] = orphans
        out[pid] = {"suites": len(suites), "sections": sections,
                    "cases": cases, "runs": runs, "tests": tests,
                    "results": results}
    return out


def db_counts(session):
    out = {}
    for pid in project_ids():
        suites = session.scalar(select(func.count()).select_from(models.Suite)
                                .where(models.Suite.project_id == pid))
        sections = session.scalar(
            select(func.count()).select_from(models.Section)
            .join(models.Suite, models.Section.suite_id == models.Suite.id)
            .where(models.Suite.project_id == pid))
        cases = session.scalar(
            select(func.count()).select_from(models.Case)
            .join(models.Suite, models.Case.suite_id == models.Suite.id)
            .where(models.Suite.project_id == pid))
        runs = session.scalar(select(func.count()).select_from(models.Run)
                              .where(models.Run.project_id == pid))
        tests = session.scalar(
            select(func.count()).select_from(models.Test)
            .join(models.Run, models.Test.run_id == models.Run.id)
            .where(models.Run.project_id == pid))
        results = session.scalar(
            select(func.count()).select_from(models.Result)
            .join(models.Test, models.Result.test_id == models.Test.id)
            .join(models.Run, models.Test.run_id == models.Run.id)
            .where(models.Run.project_id == pid))
        out[pid] = {"suites": suites, "sections": sections, "cases": cases,
                    "runs": runs, "tests": tests, "results": results}
    return out


def compare_counts(session):
    log("== sayim karsilastirmasi (TestRail dump  vs  veritabani) ==")
    names = {p["id"]: p["name"] for p in read("meta/projects.json")}
    raw, db = raw_counts(), db_counts(session)
    cols = ["suites", "sections", "cases", "runs", "tests", "results"]
    header = f"{'proje':<30}" + "".join(f"{c:>12}" for c in cols)
    log(header)
    totals_raw = dict.fromkeys(cols, 0)
    totals_db = dict.fromkeys(cols, 0)
    for pid in sorted(raw):
        line = f"{names.get(pid, pid)[:29]:<30}"
        for c in cols:
            r, d = raw[pid][c], db[pid][c]
            totals_raw[c] += r
            totals_db[c] += d
            line += f"{d:>12}" if r == d else f"{str(d) + '/' + str(r):>12}"
            if r != d:
                fail(f"{names.get(pid, pid)}: {c} dump={r} db={d}")
        log(line)
    log(f"{'TOPLAM':<30}" + "".join(f"{totals_db[c]:>12}" for c in cols))
    for c in cols:
        if totals_raw[c] != totals_db[c]:
            fail(f"toplam {c}: dump={totals_raw[c]} db={totals_db[c]}")

    # said out loud rather than quietly left out of the comparison
    skipped = sum(ORPHANS.values())
    if skipped:
        log("")
        log(f"  not: {skipped} sonuc, ait oldugu test kosumdan"
            " cikarildigi icin aktarilamadi")
        for pid, n in sorted(ORPHANS.items(), key=lambda kv: -kv[1]):
            if n:
                log(f"       {names.get(pid, pid)[:40]:<42} {n}")


def compare_cases(session):
    """Field-level spot check on randomly sampled cases."""
    log(f"== alan bazinda ornekleme ({SAMPLE} case) ==")
    files = glob.glob(os.path.join(RAW, "projects", "*", "suite_*", "cases.json"))
    random.seed(1234)
    picked = []
    for f in random.sample(files, min(len(files), 60)):
        with open(f, encoding="utf-8") as fh:
            cases = json.load(fh)
        if cases:
            picked += random.sample(cases, min(len(cases), max(1, SAMPLE // 60)))
    picked = picked[:SAMPLE]

    checked = 0
    for c in picked:
        row = session.get(models.Case, c["id"])
        if row is None:
            fail(f"case {c['id']} veritabaninda yok")
            continue
        if row.title != c["title"]:
            fail(f"case {c['id']} baslik farkli")
        if row.section_id != c["section_id"]:
            fail(f"case {c['id']} section farkli")
        if bool(c.get("is_deleted", 0)) != row.is_deleted:
            fail(f"case {c['id']} is_deleted farkli")

        # every non-empty custom_* value must survive
        for k, v in c.items():
            if not k.startswith("custom_") or v in (None, "", []):
                continue
            if k == "custom_steps_separated":
                if len(row.steps) != len(v):
                    fail(f"case {c['id']} adim sayisi dump={len(v)} db={len(row.steps)}")
                else:
                    for i, st in enumerate(v):
                        if (row.steps[i].content or None) != (st.get("content") or None):
                            fail(f"case {c['id']} adim {i} icerik farkli")
                        if (row.steps[i].expected or None) != (st.get("expected") or None):
                            fail(f"case {c['id']} adim {i} beklenen farkli")
                continue
            if row.custom.get(k) != v:
                fail(f"case {c['id']} ozel alan {k} farkli")
        checked += 1
    log(f"  kontrol edilen case: {checked}")


def compare_results(session):
    log("== sonuc ornekleme ==")
    files = glob.glob(os.path.join(RAW, "projects", "*", "run_*", "results.json"))
    if not files:
        log("  sonuc dosyasi yok, atlandi")
        return
    random.seed(99)
    checked = 0
    for f in random.sample(files, min(len(files), 40)):
        with open(f, encoding="utf-8") as fh:
            results = json.load(fh)
        for r in results[:5]:
            row = session.get(models.Result, r["id"])
            if row is None:
                fail(f"sonuc {r['id']} veritabaninda yok")
                continue
            if row.status_id != r.get("status_id"):
                fail(f"sonuc {r['id']} status farkli")
            if (row.comment or None) != (r.get("comment") or None):
                fail(f"sonuc {r['id']} yorum farkli")
            steps = r.get("custom_step_results") or []
            if len(row.step_results) != len(steps):
                fail(f"sonuc {r['id']} adim sonucu sayisi "
                     f"dump={len(steps)} db={len(row.step_results)}")
            checked += 1
    log(f"  kontrol edilen sonuc: {checked}")


def check_integrity(session):
    """Orphans and dangling references the foreign keys cannot catch."""
    log("== butunluk ==")
    checks = [
        ("parent'i olmayan section",
         "SELECT count(*) FROM sections s WHERE s.parent_id IS NOT NULL "
         "AND NOT EXISTS (SELECT 1 FROM sections p WHERE p.id = s.parent_id)"),
        ("suite'i olmayan case",
         "SELECT count(*) FROM cases c WHERE NOT EXISTS "
         "(SELECT 1 FROM suites s WHERE s.id = c.suite_id)"),
        ("case'i olmayan test",
         "SELECT count(*) FROM tests t WHERE t.case_id IS NOT NULL AND NOT EXISTS "
         "(SELECT 1 FROM cases c WHERE c.id = t.case_id)"),
        ("adimsiz ama steps sablonlu case", None),
    ]
    for label, sql in checks:
        if sql is None:
            continue
        n = session.execute(text(sql)).scalar()
        log(f"  {label:<34} {n}")
        if n:
            fail(f"{label}: {n}")


def main():
    from app.config import get_settings
    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        compare_counts(session)
        compare_cases(session)
        compare_results(session)
        check_integrity(session)

    log("")
    if problems:
        log(f"SONUC: {len(problems)} SORUN BULUNDU")
        for p in problems[:40]:
            log(f"  - {p}")
        sys.exit(1)
    log("SONUC: dump ile veritabani birebir ortusuyor")


if __name__ == "__main__":
    main()
