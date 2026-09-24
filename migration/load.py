"""Load the raw TestRail dump in data/raw into PostgreSQL.

Design notes
------------
TestRail primary keys are carried over verbatim as our primary keys. It costs
nothing (they are unique integers), and it buys a great deal: every
``C15477`` in a JMeter job, Jira ticket or automation script keeps resolving,
and the migration can be verified by comparing ids rather than by trusting a
mapping table. Sequences are bumped past the highest imported id at the end so
that new rows do not collide.

The loader is idempotent: every insert is an upsert keyed on the primary key,
so a partial run can simply be repeated.
"""
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "backend"))
from app import models  # noqa: E402
from app.models import Base  # noqa: E402

RAW = os.path.join("data", "raw")
CHUNK = 2000

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass


def log(msg):
    print(msg, flush=True)


# --- helpers ---------------------------------------------------------------

def stable_id(*parts):
    """Deterministic 62-bit id derived from TestRail's own identifiers."""
    digest = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:15], 16)


def uid(value):
    """A user reference, or None.

    TestRail writes 0 for "nobody" in older rows -- there is no user 0, so it
    has to become NULL or the foreign key rejects the batch.
    """
    return value or None


def ts(value):
    """TestRail hands out unix seconds; store real timestamps."""
    if value in (None, "", 0):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def read(rel, default=None):
    path = os.path.join(RAW, rel)
    if not os.path.exists(path):
        return default if default is not None else []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def upsert(session, model, rows, index_elements=("id",)):
    """Insert rows, updating any that already exist."""
    if not rows:
        return 0
    table = model.__table__
    cols = {c.name for c in table.columns}
    total = 0
    for i in range(0, len(rows), CHUNK):
        chunk = [{k: v for k, v in r.items() if k in cols} for r in rows[i:i + CHUNK]]
        stmt = insert(table).values(chunk)
        update = {c: stmt.excluded[c] for c in chunk[0]
                  if c not in index_elements and c in cols}
        stmt = (stmt.on_conflict_do_update(index_elements=list(index_elements),
                                           set_=update)
                if update else
                stmt.on_conflict_do_nothing(index_elements=list(index_elements)))
        session.execute(stmt)
        total += len(chunk)
    session.commit()
    return total


FIELD_TYPES = {
    1: "string", 2: "integer", 3: "text", 4: "url", 5: "checkbox",
    6: "dropdown", 7: "user", 8: "date", 9: "milestone", 10: "steps",
    11: "step_results", 12: "multiselect", 13: "bdd", 14: "bdd_results",
    16: "rating",
}

# fields TestRail reports as "custom" that we model as real columns instead
NATIVE_FIELDS = {"refs", "estimate", "milestone_id"}


def projects_on_disk():
    root = os.path.join(RAW, "projects")
    if not os.path.isdir(root):
        return []
    return sorted(int(d) for d in os.listdir(root)
                  if d.isdigit() and os.path.isdir(os.path.join(root, d)))


def suites_on_disk(pid):
    pdir = os.path.join(RAW, "projects", str(pid))
    return sorted(int(d.split("_")[1]) for d in os.listdir(pdir)
                  if d.startswith("suite_"))


def runs_on_disk(pid):
    pdir = os.path.join(RAW, "projects", str(pid))
    return sorted(int(d.split("_")[1]) for d in os.listdir(pdir)
                  if d.startswith("run_"))


# --- phase 1: vocabularies and people --------------------------------------

def load_catalog(session):
    log("== katalog ==")
    n = upsert(session, models.Role, [
        {"id": r["id"], "testrail_id": r["id"], "name": r["name"],
         "is_default": r.get("is_default", False),
         "is_project_default": r.get("is_project_default", False),
         "permissions": {}}
        for r in read("meta/roles.json")])
    log(f"  roles            {n}")

    n = upsert(session, models.User, [
        {"id": u["id"], "testrail_id": u["id"], "email": u["email"],
         "name": u["name"], "is_active": u.get("is_active", True),
         "role_id": u.get("role_id")}
        for u in read("meta/users.json")])
    log(f"  users            {n}")

    groups = read("meta/groups.json")
    n = upsert(session, models.Group, [
        {"id": g["id"], "testrail_id": g["id"], "name": g["name"]}
        for g in groups])
    log(f"  groups           {n}")
    members = [{"group_id": g["id"], "user_id": uid}
               for g in groups for uid in g.get("user_ids", [])]
    if members:
        session.execute(text("DELETE FROM group_members"))
        session.execute(models.GroupMember.__table__.insert(), members)
        session.commit()
    log(f"  group_members    {len(members)}")

    n = upsert(session, models.CaseType, [
        {"id": t["id"], "testrail_id": t["id"], "name": t["name"],
         "is_default": t.get("is_default", False)}
        for t in read("meta/case_types.json")])
    log(f"  case_types       {n}")

    n = upsert(session, models.Priority, [
        {"id": p["id"], "testrail_id": p["id"], "name": p["name"],
         "short_name": p.get("short_name"),
         "priority_level": p.get("priority", 0),
         "is_default": p.get("is_default", False)}
        for p in read("meta/priorities.json")])
    log(f"  priorities       {n}")

    n = upsert(session, models.Status, [
        {"id": s["id"], "testrail_id": s["id"], "name": s["name"],
         "label": s.get("label") or s["name"],
         # color_medium is what TestRail paints the status dots and badges
         # with; color_dark is the muted text shade and reads as mud on white
         "color": f"#{s['color_medium']:06x}" if s.get("color_medium") else None,
         "is_system": s.get("is_system", False),
         "is_untested": s.get("is_untested", False),
         "is_final": s.get("is_final", True)}
        for s in read("meta/statuses.json")])
    log(f"  statuses         {n}")


def load_custom_fields(session):
    rows, options = [], []
    for entity, fname in (("case", "case_fields"), ("result", "result_fields")):
        for f in read(f"meta/{fname}.json"):
            if f.get("system_name") in NATIVE_FIELDS:
                continue
            fid = f["id"]
            rows.append({
                "id": fid, "testrail_id": fid, "entity": entity,
                "system_name": f["system_name"], "label": f["label"],
                "description": f.get("description"),
                "field_type": FIELD_TYPES.get(f["type_id"], str(f["type_id"])),
                "is_global": any(c.get("context", {}).get("is_global")
                                 for c in f.get("configs", [])),
                "display_order": f.get("display_order", 0),
                "configs": f.get("configs", []),
            })
            # dropdown / multiselect choices are stored as "value, label" lines
            for cfg in f.get("configs", []):
                items = (cfg.get("options") or {}).get("items")
                if not items:
                    continue
                for order, line in enumerate(str(items).splitlines()):
                    if "," not in line:
                        continue
                    val, _, label = line.partition(",")
                    if val.strip().isdigit():
                        options.append({"field_id": fid,
                                        "value": int(val.strip()),
                                        "label": label.strip(),
                                        "display_order": order})
    log(f"  custom_fields    {upsert(session, models.CustomField, rows)}")
    if options:
        # de-duplicate: the same option list can repeat across project configs
        seen, uniq = set(), []
        for o in options:
            key = (o["field_id"], o["value"])
            if key not in seen:
                seen.add(key)
                uniq.append(o)
        session.execute(text("DELETE FROM custom_field_options"))
        session.execute(models.CustomFieldOption.__table__.insert(), uniq)
        session.commit()
        log(f"  field_options    {len(uniq)}")


def load_projects(session):
    log("== projeler ==")
    projects = read("meta/projects.json")
    n = upsert(session, models.Project, [
        {"id": p["id"], "testrail_id": p["id"], "name": p["name"],
         "announcement": p.get("announcement"),
         "show_announcement": p.get("show_announcement", False),
         "is_completed": p.get("is_completed", False),
         "completed_on": ts(p.get("completed_on")),
         "suite_mode": p.get("suite_mode", 3)}
        for p in projects])
    log(f"  projects         {n}")

    known = {u["id"] for u in read("meta/users.json")}
    members = [{"project_id": p["id"], "user_id": u["user_id"],
                "role_id": u.get("project_role_id")}
               for p in projects for u in p.get("users", [])
               if u["user_id"] in known]
    if members:
        session.execute(text("DELETE FROM project_members"))
        session.execute(models.ProjectMember.__table__.insert(), members)
        session.commit()
    log(f"  project_members  {len(members)}")

    # templates are returned per project but are instance-wide objects
    tpl = {}
    for pid in projects_on_disk():
        for t in read(f"projects/{pid}/templates.json"):
            tpl[t["id"]] = {"id": t["id"], "testrail_id": t["id"],
                            "name": t["name"],
                            "is_default": t.get("is_default", False)}
    log(f"  templates        {upsert(session, models.Template, list(tpl.values()))}")


def load_milestones(session):
    """Load milestones, including the sub-milestones TestRail hides.

    ``get_milestones`` returns only top-level milestones. Children exist
    nowhere else in the API: they appear solely inside the parent's
    ``get_milestone`` detail, under a nested ``milestones`` key. On this
    instance that is 195 of 558 milestones, so walking the nesting is not
    an optimisation -- skipping it loses a third of them.
    """
    log("== milestone ==")
    rows = []

    def add(m, pid, parent_id=None):
        rows.append({
            "id": m["id"], "testrail_id": m["id"], "project_id": pid,
            "parent_id": m.get("parent_id") or parent_id, "name": m["name"],
            "description": m.get("description"), "refs": m.get("refs"),
            "start_on": ts(m.get("start_on")),
            "started_on": ts(m.get("started_on")),
            "due_on": ts(m.get("due_on")),
            "completed_on": ts(m.get("completed_on")),
            "is_started": m.get("is_started", False),
            "is_completed": m.get("is_completed", False),
        })
        for child in m.get("milestones") or []:
            add(child, pid, m["id"])

    for pid in projects_on_disk():
        for m in read(f"projects/{pid}/milestones.json"):
            detail = read(f"projects/{pid}/milestone_{m['id']}.json", default={})
            add(detail or m, pid)
    # parents first: insert without the self-reference, then fill it in
    parents = {r["id"]: r.pop("parent_id") for r in rows}
    log(f"  milestones       {upsert(session, models.Milestone, rows)}")
    linked = [{"id": mid, "parent_id": pid_}
              for mid, pid_ in parents.items()
              if pid_ and pid_ in parents]
    if linked:
        session.execute(text(
            "UPDATE milestones SET parent_id = :parent_id WHERE id = :id"),
            linked)
        session.commit()
    log(f"  alt milestone    {len(linked)}")


# --- phase 2: the case library ---------------------------------------------

def load_structure(session, only_suites: set[int] | None = None):
    """Load suites, sections and cases.

    `only_suites` narrows the pass to the suites a sync refreshed; None means
    everything, which is what the initial import wants.
    """
    log("== suite / section / case ==")
    totals = {"suites": 0, "sections": 0, "cases": 0, "steps": 0, "labels": 0}
    label_ids = {}

    for pid in projects_on_disk():
        suites = read(f"projects/{pid}/suites.json")
        totals["suites"] += upsert(session, models.Suite, [
            {"id": s["id"], "testrail_id": s["id"], "project_id": pid,
             "name": s["name"], "description": s.get("description"),
             "is_master": s.get("is_master", False),
             "is_baseline": s.get("is_baseline", False),
             "is_completed": s.get("is_completed", False),
             "completed_on": ts(s.get("completed_on"))}
            for s in suites])

        for sid in suites_on_disk(pid):
            if only_suites is not None and sid not in only_suites:
                continue
            sections = read(f"projects/{pid}/suite_{sid}/sections.json")
            # parent_id is filled in a second pass so ordering never matters
            parents = {}
            rows = []
            for s in sections:
                parents[s["id"]] = s.get("parent_id")
                rows.append({
                    "id": s["id"], "testrail_id": s["id"], "suite_id": sid,
                    "parent_id": None, "name": s["name"],
                    "description": s.get("description"),
                    "depth": s.get("depth", 0),
                    "display_order": s.get("display_order", 0),
                })
            totals["sections"] += upsert(session, models.Section, rows)
            links = [{"id": k, "parent_id": v} for k, v in parents.items() if v]
            if links:
                session.execute(text(
                    "UPDATE sections SET parent_id = :parent_id WHERE id = :id"),
                    links)
                session.commit()

            cases = read(f"projects/{pid}/suite_{sid}/cases.json")
            # TestRail hides soft-deleted cases from get_cases, but the tests
            # inside archived runs still point at them; they come in flagged
            # rather than omitted
            deleted = read(f"projects/{pid}/suite_{sid}/cases_deleted.json")
            for row in deleted:
                row["is_deleted"] = 1
            cases = cases + deleted
            case_rows, step_rows, case_labels = [], [], []
            for c in cases:
                custom = {k: v for k, v in c.items()
                          if k.startswith("custom_") and v not in (None, "", [])}
                steps = custom.pop("custom_steps_separated", None) or []
                case_rows.append({
                    "id": c["id"], "testrail_id": c["id"],
                    "section_id": c["section_id"], "suite_id": sid,
                    "title": c["title"], "template_id": c.get("template_id"),
                    "type_id": c.get("type_id"),
                    "priority_id": c.get("priority_id"),
                    "milestone_id": c.get("milestone_id"),
                    "refs": c.get("refs"), "estimate": c.get("estimate"),
                    "estimate_forecast": c.get("estimate_forecast"),
                    "display_order": c.get("display_order", 0),
                    "is_deleted": bool(c.get("is_deleted", 0)),
                    "created_by": uid(c.get("created_by")),
                    "created_on": ts(c.get("created_on")),
                    "updated_by": uid(c.get("updated_by")),
                    "updated_on": ts(c.get("updated_on")),
                    "custom": custom,
                })
                for idx, st in enumerate(steps):
                    step_rows.append({
                        "case_id": c["id"], "idx": idx,
                        "content": st.get("content"),
                        "expected": st.get("expected"),
                        "additional_info": st.get("additional_info"),
                        "refs": st.get("refs"),
                        "shared_step_id": st.get("shared_step_id"),
                    })
                for lb in c.get("labels") or []:
                    title = lb["title"] if isinstance(lb, dict) else str(lb)
                    key = (pid, title)
                    label_ids.setdefault(key, None)
                    case_labels.append((c["id"], key))

            totals["cases"] += upsert(session, models.Case, case_rows)
            if step_rows:
                ids = [r["id"] for r in case_rows]
                session.execute(
                    models.CaseStep.__table__.delete().where(
                        models.CaseStep.case_id.in_(ids)))
                for i in range(0, len(step_rows), CHUNK):
                    session.execute(models.CaseStep.__table__.insert(),
                                    step_rows[i:i + CHUNK])
                session.commit()
                totals["steps"] += len(step_rows)

            if case_labels:
                _attach_labels(session, label_ids, case_labels)
                totals["labels"] += len(case_labels)

        log(f"  p{pid:<3} ok")

    # shared steps are per project and reference no case
    shared = []
    for pid in projects_on_disk():
        for s in read(f"projects/{pid}/shared_steps.json"):
            shared.append({
                "id": s["id"], "testrail_id": s["id"], "project_id": pid,
                "title": s.get("title", ""),
                "steps": s.get("custom_steps_separated") or [],
                "created_by": uid(s.get("created_by")),
                "created_on": ts(s.get("created_on")),
                "updated_by": uid(s.get("updated_by")),
                "updated_on": ts(s.get("updated_on")),
            })
    if shared:
        log(f"  shared_steps     {upsert(session, models.SharedStep, shared)}")
    log(f"  toplam {totals}")
    return totals


def _attach_labels(session, label_ids, case_labels):
    """Create any missing labels, then link them to cases."""
    missing = [k for k, v in label_ids.items() if v is None]
    for pid, title in missing:
        existing = session.execute(
            select(models.Label.id).where(models.Label.project_id == pid,
                                          models.Label.title == title)
        ).scalar_one_or_none()
        if existing is None:
            existing = session.execute(
                models.Label.__table__.insert()
                .values(project_id=pid, title=title)
                .returning(models.Label.id)
            ).scalar_one()
        label_ids[(pid, title)] = existing
    session.commit()

    rows = [{"case_id": cid, "label_id": label_ids[key]}
            for cid, key in case_labels]
    stmt = insert(models.CaseLabel.__table__).values(rows)
    session.execute(stmt.on_conflict_do_nothing(
        index_elements=["case_id", "label_id"]))
    session.commit()


# --- phase 3: execution -----------------------------------------------------

def load_execution(session, only_runs: set[int] | None = None):
    """Load plans, runs, tests and results.

    `only_runs` narrows the per-run work to the runs a sync refreshed. Plans
    and run metadata are still read whole: they are one file per project and
    a run's own row may have changed (completed, renamed) without any new
    result landing in it.
    """
    log("== plan / run / test / result ==")
    totals = {"plans": 0, "entries": 0, "runs": 0, "tests": 0,
              "results": 0, "steps": 0}
    # one query rather than one per test batch: 65k ids fit in memory easily
    known_cases = set(session.scalars(select(models.Case.id)))
    log(f"  bilinen case: {len(known_cases)}")

    for pid in projects_on_disk():
        groups, configs = [], []
        for g in read(f"projects/{pid}/configs.json"):
            groups.append({"id": g["id"], "testrail_id": g["id"],
                           "project_id": pid, "name": g["name"]})
            for c in g.get("configs", []):
                configs.append({"id": c["id"], "testrail_id": c["id"],
                                "group_id": g["id"], "name": c["name"]})
        upsert(session, models.ConfigGroup, groups)
        upsert(session, models.Config, configs)

        plans = read(f"projects/{pid}/plans.json")
        archived_plans = read(f"projects/{pid}/plans_archived.json")
        archived_plan_ids = {p["id"] for p in archived_plans}
        plans = plans + archived_plans
        plan_rows, entry_rows = [], []
        entry_pk = {}
        for p in plans:
            plan_rows.append({
                "id": p["id"], "testrail_id": p["id"], "project_id": pid,
                "milestone_id": p.get("milestone_id"), "name": p["name"],
                "description": p.get("description"),
                "assignedto_id": uid(p.get("assignedto_id")),
                "is_completed": p.get("is_completed", False),
                "completed_on": ts(p.get("completed_on")),
                "created_by": uid(p.get("created_by")),
                "created_on": ts(p.get("created_on")),
                "is_archived": p["id"] in archived_plan_ids,
            })
            detail = read(f"projects/{pid}/plan_{p['id']}.json", default={})
            for order, e in enumerate(detail.get("entries", [])):
                # entry ids are uuids in TestRail; derive a stable integer pk.
                # hash() would do, but it is salted per process, so a re-run
                # would mint new ids and duplicate every entry.
                pk = stable_id(p["id"], e.get("id", order))
                entry_pk[e.get("id")] = pk
                entry_rows.append({
                    "id": pk, "testrail_uuid": str(e.get("id")),
                    "plan_id": p["id"], "suite_id": e.get("suite_id"),
                    "name": e.get("name"), "display_order": order,
                })
        totals["plans"] += upsert(session, models.Plan, plan_rows)
        totals["entries"] += upsert(session, models.PlanEntry, entry_rows)

        # runs: the standalone ones plus every run nested inside a plan
        run_rows = []
        seen_runs = set()
        archived_run_ids = {r["id"] for r in
                            read(f"projects/{pid}/runs_archived.json")}

        def add_run(r, entry_uuid=None):
            if r["id"] in seen_runs:
                return
            seen_runs.add(r["id"])
            run_rows.append({
                "id": r["id"], "testrail_id": r["id"], "project_id": pid,
                "suite_id": r.get("suite_id"),
                "plan_entry_id": entry_pk.get(entry_uuid),
                "milestone_id": r.get("milestone_id"),
                "name": r.get("name", ""), "description": r.get("description"),
                "refs": r.get("refs"),
                "include_all": r.get("include_all", True),
                "is_completed": r.get("is_completed", False),
                "completed_on": ts(r.get("completed_on")),
                "assignedto_id": uid(r.get("assignedto_id")),
                "created_by": uid(r.get("created_by")),
                "created_on": ts(r.get("created_on")),
                "config": r.get("config"),
                "config_ids": r.get("config_ids") or [],
                "is_archived": r["id"] in archived_run_ids,
            })

        for p in plans:
            detail = read(f"projects/{pid}/plan_{p['id']}.json", default={})
            for e in detail.get("entries", []):
                for r in e.get("runs", []):
                    add_run(r, e.get("id"))
        for r in read(f"projects/{pid}/runs.json"):
            add_run(r)
        for r in read(f"projects/{pid}/runs_archived.json"):
            add_run(r)
        totals["runs"] += upsert(session, models.Run, run_rows)

        wanted = runs_on_disk(pid)
        if only_runs is not None:
            wanted = [r for r in wanted if r in only_runs]
        for rid in wanted:
            tests = read(f"projects/{pid}/run_{rid}/tests.json")
            known_tests = {t["id"] for t in tests}
            totals["tests"] += upsert(session, models.Test, [
                {"id": t["id"], "testrail_id": t["id"], "run_id": rid,
                 # a case hard-deleted in TestRail leaves the test behind;
                 # the title snapshot is what the run actually executed
                 "case_id": (t.get("case_id")
                             if t.get("case_id") in known_cases else None),
                 "title": t.get("title", ""),
                 "status_id": t.get("status_id"),
                 "assignedto_id": uid(t.get("assignedto_id")),
                 "type_id": t.get("type_id"),
                 "priority_id": t.get("priority_id"),
                 "template_id": t.get("template_id"),
                 "milestone_id": t.get("milestone_id"),
                 "refs": t.get("refs"), "estimate": t.get("estimate"),
                 "estimate_forecast": t.get("estimate_forecast"),
                 "custom": {k: v for k, v in t.items()
                            if k.startswith("custom_") and v not in (None, "", [])}}
                for t in tests])

            results = read(f"projects/{pid}/run_{rid}/results.json")
            res_rows, step_rows = [], []
            for r in results:
                # get_results_for_run also returns results belonging to tests
                # that were removed from the run later; there is no row left
                # to hang them on, so they are counted and skipped
                if r.get("test_id") not in known_tests:
                    totals["orphan_results"] = totals.get("orphan_results", 0) + 1
                    continue
                custom = {k: v for k, v in r.items()
                          if k.startswith("custom_") and v not in (None, "", [])}
                steps = custom.pop("custom_step_results", None) or []
                res_rows.append({
                    "id": r["id"], "testrail_id": r["id"],
                    "test_id": r["test_id"], "status_id": r.get("status_id"),
                    "created_by": uid(r.get("created_by")),
                    "created_on": ts(r.get("created_on")) or ts(1),
                    "assignedto_id": uid(r.get("assignedto_id")),
                    "comment": r.get("comment"), "version": r.get("version"),
                    "elapsed": r.get("elapsed"), "defects": r.get("defects"),
                    "custom": custom,
                })
                for idx, st in enumerate(steps):
                    step_rows.append({
                        "result_id": r["id"], "idx": idx,
                        "content": st.get("content"),
                        "expected": st.get("expected"),
                        "actual": st.get("actual"),
                        "status_id": st.get("status_id"),
                    })
            totals["results"] += upsert(session, models.Result, res_rows)
            if step_rows:
                session.execute(
                    models.ResultStep.__table__.delete().where(
                        models.ResultStep.result_id.in_(
                            [r["id"] for r in res_rows])))
                for i in range(0, len(step_rows), CHUNK):
                    session.execute(models.ResultStep.__table__.insert(),
                                    step_rows[i:i + CHUNK])
                session.commit()
                totals["steps"] += len(step_rows)

        log(f"  p{pid:<3} ok  {totals}")
    log(f"  toplam {totals}")
    return totals


def load_attachments(session):
    """Register downloaded attachment blobs.

    The text that references an attachment is stored exactly as TestRail
    wrote it, ``index.php?/attachments/get/<id>`` and all. Rewriting it here
    would mean editing 64k rows of user content to suit our URL scheme, and
    losing the ability to diff against TestRail. The API rewrites the
    reference when it serves the field instead.
    """
    log("== ekler ==")
    index = read("attachments_index.json")
    if not index:
        log("  attachments_index.json yok - once fetch_blobs.py calistirin")
        return

    rows = []
    for a in index:
        if not a.get("storage_key"):
            continue  # could not be downloaded; recorded in the report instead
        rows.append({
            "testrail_id": str(a["id"]),
            "entity_type": a.get("entity_type") or "inline",
            "entity_id": a.get("entity_id"),
            "filename": a.get("filename") or str(a["id"]),
            "size": a.get("bytes") or a.get("size"),
            "content_type": a.get("content_type"),
            "storage_key": a["storage_key"],
            "checksum_sha256": a.get("checksum_sha256"),
            "is_inline": bool(a.get("is_inline")),
            "project_id": a.get("project_id"),
            "created_by": uid(a.get("created_by")),
            "created_on": ts(a.get("created_on")),
        })
    n = upsert(session, models.Attachment, rows,
               index_elements=("testrail_id",))
    log(f"  attachments      {n}")

    missing = [a for a in index if not a.get("storage_key")]
    if missing:
        log(f"  indirilemeyen    {len(missing)} (data/raw/attachments_failed.json)")


def load_history(session, only_cases: set[int] | None = None):
    """Load case edit history.

    `only_cases` narrows the pass to the cases a sync refreshed; the full
    pass globs 65,227 files, which a weekly sync has no reason to do.
    """
    log("== case gecmisi ==")
    if only_cases is not None:
        files = [os.path.join(RAW, "history", f"case_{cid}.json")
                 for cid in sorted(only_cases)]
        files = [f for f in files if os.path.exists(f)]
    else:
        files = glob.glob(os.path.join(RAW, "history", "case_*.json"))
    if not files:
        log("  gecmis dosyasi yok - once 'dump.py history' calistirin")
        return {"entries": 0}

    known = set(session.execute(select(models.Case.id)).scalars())
    rows, skipped = [], 0
    for path in files:
        case_id = int(os.path.basename(path)[5:-5])
        if case_id not in known:
            skipped += 1
            continue
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)
        for e in entries:
            rows.append({
                "id": stable_id("history", case_id, e.get("id", "")),
                "case_id": case_id,
                "user_id": uid(e.get("user_id")),
                "created_on": ts(e.get("created_on")) or ts(1),
                "changes": e.get("changes") or [],
                "source": "testrail",
            })
        if len(rows) >= 20000:
            upsert(session, models.CaseHistory, rows)
            log(f"  ... {len(rows)} kayit yazildi")
            rows = []
    total = upsert(session, models.CaseHistory, rows) if rows else 0
    count = session.scalar(select(func.count()).select_from(models.CaseHistory))
    log(f"  case_history     {count} (son parti {total}, atlanan case {skipped})")
    return {"entries": count}


# --- finishing up ----------------------------------------------------------

def fix_sequences(session):
    """Move every identity sequence past the highest imported id."""
    log("== sequence duzeltme ==")
    for table in Base.metadata.tables.values():
        pk = list(table.primary_key.columns)
        if len(pk) != 1 or not pk[0].autoincrement:
            continue
        col = pk[0].name
        session.execute(text(
            f"SELECT setval(pg_get_serial_sequence('{table.name}', '{col}'), "
            f"GREATEST((SELECT COALESCE(MAX({col}), 0) FROM {table.name}), 1))"
        ))
    session.commit()
    log("  ok")


def main():
    from app.config import get_settings

    url = os.environ.get("DATABASE_URL") or get_settings().database_url
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)

    phase = sys.argv[1] if len(sys.argv) > 1 else "all"
    with Session(engine) as session:
        if phase in ("catalog", "all"):
            load_catalog(session)
            load_custom_fields(session)
            load_projects(session)
            load_milestones(session)
        if phase in ("structure", "all"):
            load_structure(session)
        if phase in ("execution", "all"):
            load_execution(session)
        if phase in ("attachments", "all"):
            load_attachments(session)
        if phase in ("history", "all"):
            load_history(session)
        # Always, not just on a full run. Running the phases one at a time
        # used to leave every sequence at its starting value while the
        # imported rows sat at ids in the millions, so the first row the
        # application created would collide.
        fix_sequences(session)

        log("== satir sayilari ==")
        for name, model in sorted(
                (m.__tablename__, m) for m in Base.registry._class_registry.values()
                if hasattr(m, "__tablename__")):
            count = session.execute(
                select(func.count()).select_from(model.__table__)).scalar()
            log(f"  {name:<22} {count}")


if __name__ == "__main__":
    main()

