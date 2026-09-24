"""Search and export.

TestRail puts a search box in the masthead and people live in it -- with
64k cases, browsing the tree is not how anyone finds a specific scenario.
"""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ...db import get_session
from ...models import (Case, CaseStep, CaseType, Milestone, Priority, Run,
                       Section, Suite, User)
from ..deps import current_user

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
def search(q: str = Query(min_length=2),
           project_id: int | None = None,
           limit: int = 40,
           session: Session = Depends(get_session),
           _: User = Depends(current_user)):
    """One call, several kinds of hit: a case id, a case title, a run, a
    milestone. Typing C15477 should land on that case, not search for it."""
    term = q.strip()
    like = f"%{term}%"
    out: dict[str, list] = {"cases": [], "runs": [], "milestones": []}

    # "C15477" or a bare id is an exact lookup, not a text search
    bare = term[1:] if term[:1].upper() == "C" else term
    if bare.isdigit():
        case = session.get(Case, int(bare))
        if case is not None:
            out["cases"].append({"id": case.id, "title": case.title,
                                 "suite_id": case.suite_id,
                                 "section_id": case.section_id, "exact": True})

    suite_ids = None
    if project_id:
        suite_ids = select(Suite.id).where(
            Suite.project_id == project_id).scalar_subquery()

    where = [Case.is_deleted.is_(False),
             or_(Case.title.ilike(like), Case.refs.ilike(like))]
    if suite_ids is not None:
        where.append(Case.suite_id.in_(suite_ids))
    rows = session.scalars(
        select(Case).where(*where).order_by(Case.updated_on.desc().nulls_last())
        .limit(limit)).all()
    seen = {c["id"] for c in out["cases"]}
    out["cases"] += [{"id": c.id, "title": c.title, "suite_id": c.suite_id,
                      "section_id": c.section_id, "exact": False}
                     for c in rows if c.id not in seen]

    run_where = [Run.name.ilike(like)]
    if project_id:
        run_where.append(Run.project_id == project_id)
    out["runs"] = [{"id": r.id, "name": r.name, "project_id": r.project_id}
                   for r in session.scalars(
                       select(Run).where(*run_where)
                       .order_by(Run.created_on.desc().nulls_last())
                       .limit(15))]

    ms_where = [Milestone.name.ilike(like)]
    if project_id:
        ms_where.append(Milestone.project_id == project_id)
    out["milestones"] = [{"id": m.id, "name": m.name, "project_id": m.project_id}
                         for m in session.scalars(
                             select(Milestone).where(*ms_where).limit(15))]

    out["total"] = sum(len(v) for v in out.values() if isinstance(v, list))
    return out


@router.get("/suites/{suite_id}/cases.csv")
def export_cases(suite_id: int,
                 section_id: int | None = None,
                 session: Session = Depends(get_session),
                 _: User = Depends(current_user)):
    """CSV of a suite, steps flattened into one cell per case.

    Exports are how people get data out when a tool cannot answer their
    question; refusing to provide one is how a tool becomes the next thing
    somebody wants to migrate away from.
    """
    where = [Case.suite_id == suite_id, Case.is_deleted.is_(False)]
    if section_id:
        where.append(Case.section_id == section_id)

    rows = session.execute(
        select(Case, Section.name, CaseType.name, Priority.name, User.name)
        .join(Section, Case.section_id == Section.id)
        .outerjoin(CaseType, Case.type_id == CaseType.id)
        .outerjoin(Priority, Case.priority_id == Priority.id)
        .outerjoin(User, Case.created_by == User.id)
        .where(*where)
        .order_by(Case.section_id, Case.display_order)).all()

    steps: dict[int, list[CaseStep]] = {}
    for step in session.scalars(
            select(CaseStep).where(CaseStep.case_id.in_([r[0].id for r in rows]))
            .order_by(CaseStep.case_id, CaseStep.idx)):
        steps.setdefault(step.case_id, []).append(step)

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["ID", "Bölüm", "Başlık", "Tip", "Öncelik", "Referans",
                     "Oluşturan", "Oluşturma", "Güncelleme", "Adım sayısı",
                     "Adımlar", "Beklenen sonuçlar"])
    for case, section_name, type_name, priority_name, author in rows:
        mine = steps.get(case.id, [])
        writer.writerow([
            f"C{case.id}", section_name, case.title, type_name or "",
            priority_name or "", case.refs or "", author or "",
            case.created_on.strftime("%Y-%m-%d") if case.created_on else "",
            case.updated_on.strftime("%Y-%m-%d") if case.updated_on else "",
            len(mine),
            " | ".join((s.content or "").replace("\n", " ") for s in mine),
            " | ".join((s.expected or "").replace("\n", " ") for s in mine),
        ])

    buffer.seek(0)
    suite = session.get(Suite, suite_id)
    name = (suite.name if suite else f"suite-{suite_id}").replace(" ", "_")
    # BOM so Excel opens Turkish characters correctly on Windows
    data = "﻿" + buffer.getvalue()
    return StreamingResponse(
        io.BytesIO(data.encode("utf-8")), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})


@router.get("/projects/{project_id}/case-field-values")
def field_values(project_id: int, field: str,
                 session: Session = Depends(get_session),
                 _: User = Depends(current_user)):
    """Distinct values a custom field actually takes in this project, so the
    filter offers real choices instead of the whole option list."""
    suite_ids = select(Suite.id).where(
        Suite.project_id == project_id).scalar_subquery()
    rows = session.execute(
        select(Case.custom[field].astext, func.count())
        .where(Case.suite_id.in_(suite_ids), Case.custom.has_key(field))
        .group_by(Case.custom[field].astext)
        .order_by(func.count().desc()).limit(40)).all()
    return [{"value": v, "count": n} for v, n in rows if v not in (None, "", "0")]
