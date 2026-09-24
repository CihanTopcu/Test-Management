"""The case library: suites, the section tree and case CRUD."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...audit import record
from ...db import get_session
from ...models import (Attachment, Case, CaseHistory, CaseStep, Run, Section,
                       Suite, Test, User)
from ..deps import current_user
from ..permissions import WRITE_CASES, assert_can
from ..rendering import referenced_ids, rewrite_deep
from ..schemas import (CaseCreate, CaseOut, CasePage, CaseSummary, CaseUpdate,
                       SectionCreate, SectionNode, SectionOut, SectionUpdate,
                       SuiteCreate, SuiteOut, SuiteUpdate)

router = APIRouter(prefix="/api", tags=["cases"])


def _available(session: Session, ids: set[str]) -> set[str]:
    """Which of these attachment ids do we actually hold bytes for?"""
    if not ids:
        return set()
    return set(session.scalars(
        select(Attachment.testrail_id).where(Attachment.testrail_id.in_(ids))))


def _render_case(session: Session, case: Case) -> CaseOut:
    out = CaseOut.model_validate(case)
    ids = referenced_ids(out.custom) | referenced_ids(
        [s.model_dump() for s in out.steps])
    if ids:
        have = _available(session, ids)
        out.custom = rewrite_deep(out.custom, have)
        for step in out.steps:
            step.content = rewrite_deep(step.content, have)
            step.expected = rewrite_deep(step.expected, have)
            step.additional_info = rewrite_deep(step.additional_info, have)
    return out


@router.get("/projects/{project_id}/suites", response_model=list[SuiteOut])
def list_suites(project_id: int, session: Session = Depends(get_session),
                _: User = Depends(current_user)):
    """Suites with their section, case and run counts.

    The suite list is the first thing anyone sees in a project, and a bare
    list of names tells them nothing about where the work is.
    """
    suites = session.scalars(
        select(Suite).where(Suite.project_id == project_id)
        .order_by(Suite.name)).all()
    if not suites:
        return []
    ids = [s.id for s in suites]

    sections = dict(session.execute(
        select(Section.suite_id, func.count())
        .where(Section.suite_id.in_(ids)).group_by(Section.suite_id)).all())
    cases = dict(session.execute(
        select(Case.suite_id, func.count())
        .where(Case.suite_id.in_(ids), Case.is_deleted.is_(False))
        .group_by(Case.suite_id)).all())
    runs = dict(session.execute(
        select(Run.suite_id, func.count())
        .where(Run.suite_id.in_(ids)).group_by(Run.suite_id)).all())

    out = []
    for suite in suites:
        row = SuiteOut.model_validate(suite)
        row.section_count = sections.get(suite.id, 0)
        row.case_count = cases.get(suite.id, 0)
        row.run_count = runs.get(suite.id, 0)
        out.append(row)
    return out


@router.post("/projects/{project_id}/suites", response_model=SuiteOut,
             status_code=201)
def create_suite(project_id: int, payload: SuiteCreate,
                 session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    assert_can(session, user, WRITE_CASES, project_id)
    suite = Suite(project_id=project_id, name=payload.name,
                  description=payload.description)
    session.add(suite)
    session.commit()
    session.refresh(suite)
    return SuiteOut.model_validate(suite)


@router.post("/sections", response_model=SectionOut, status_code=201)
def create_section(payload: SectionCreate,
                   session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    suite = session.get(Suite, payload.suite_id)
    if suite is None:
        raise HTTPException(404, "suite bulunamadi")
    assert_can(session, user, WRITE_CASES, suite.project_id)
    parent = session.get(Section, payload.parent_id) if payload.parent_id else None
    order = session.scalar(
        select(func.coalesce(func.max(Section.display_order), 0))
        .where(Section.suite_id == payload.suite_id)) or 0
    section = Section(
        suite_id=payload.suite_id, parent_id=payload.parent_id,
        name=payload.name, description=payload.description,
        depth=(parent.depth + 1) if parent else 0,
        display_order=order + 1,
    )
    session.add(section)
    session.commit()
    session.refresh(section)
    return SectionOut.model_validate(section)


@router.patch("/suites/{suite_id}", response_model=SuiteOut)
def update_suite(suite_id: int, payload: SuiteUpdate,
                 session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    suite = session.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(404, "suite bulunamadi")
    assert_can(session, user, WRITE_CASES, suite.project_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(suite, key, value)
    session.commit()
    session.refresh(suite)
    return SuiteOut.model_validate(suite)


@router.delete("/suites/{suite_id}", status_code=204)
def delete_suite(suite_id: int, request: Request,
                 session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    """Refuse while anything still points at the suite.

    A suite holds thousands of cases and the runs that executed them; the
    useful answer to "delete this" is almost always "you meant one section",
    so the rule is explicit rather than cascading quietly.
    """
    suite = session.get(Suite, suite_id)
    if suite is None:
        raise HTTPException(404, "suite bulunamadi")
    assert_can(session, user, WRITE_CASES, suite.project_id)

    runs = session.scalar(select(func.count()).select_from(Run)
                          .where(Run.suite_id == suite_id)) or 0
    if runs:
        raise HTTPException(400, f"{runs} kosum bu suite'e bagli, once onlari silin")
    cases = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id == suite_id, Case.is_deleted.is_(False))) or 0
    if cases:
        raise HTTPException(400, f"{cases} case iceriyor, once bolumleri bosaltin")
    kept = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.suite_id == suite_id)) or 0
    if kept:
        raise HTTPException(
            400, f"{kept} silinmis case'in gecmisi bu suite'e bagli, suite silinemez")

    session.execute(Section.__table__.delete().where(Section.suite_id == suite_id))
    record(session, user, "delete", "suite", suite_id, label=suite.name,
           project_id=suite.project_id, request=request)
    session.delete(suite)
    session.commit()


@router.patch("/sections/{section_id}", response_model=SectionOut)
def update_section(section_id: int, payload: SectionUpdate,
                   session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    """Rename a section, or move it under a different parent.

    Moving a subtree has to re-stamp depth on everything below it, otherwise
    the tree renders at the wrong indent and the sidebar nests wrongly.
    """
    section = session.get(Section, section_id)
    if section is None:
        raise HTTPException(404, "bolum bulunamadi")
    suite = session.get(Suite, section.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)

    data = payload.model_dump(exclude_unset=True)
    if "parent_id" in data:
        parent_id = data["parent_id"]
        if parent_id == section_id:
            raise HTTPException(400, "bolum kendi altina tasinamaz")
        parent = session.get(Section, parent_id) if parent_id else None
        if parent is not None:
            if parent.suite_id != section.suite_id:
                raise HTTPException(400, "hedef bolum baska bir suite'te")
            # walking up from the target catches the loop a plain parent
            # check would miss: moving a section under its own grandchild
            walker, seen = parent, 0
            while walker is not None and seen < 100:
                if walker.id == section_id:
                    raise HTTPException(400, "bolum kendi alt agacina tasinamaz")
                walker = session.get(Section, walker.parent_id) if walker.parent_id else None
                seen += 1
        section.parent_id = parent_id
        new_depth = (parent.depth + 1) if parent else 0
        shift = new_depth - section.depth
        section.depth = new_depth
        if shift:
            _shift_depth(session, section_id, shift)

    for key in ("name", "description", "display_order"):
        if key in data:
            setattr(section, key, data[key])
    session.commit()
    session.refresh(section)
    return SectionOut.model_validate(section)


def _shift_depth(session: Session, parent_id: int, shift: int) -> None:
    children = list(session.scalars(
        select(Section).where(Section.parent_id == parent_id)))
    for child in children:
        child.depth += shift
        _shift_depth(session, child.id, shift)


@router.delete("/sections/{section_id}", status_code=204)
def delete_section(section_id: int, request: Request,
                   session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    """Delete a section, its subsections and the cases in them.

    The cases are soft-deleted for the same reason a single case is: runs
    reference them, and a hard delete would rewrite the history of every run
    they appear in. Because cases.section_id cascades, the sections holding
    them have to survive as well -- so a section that ever held a case is
    hidden rather than dropped, and only a genuinely empty one is removed.
    """
    section = session.get(Section, section_id)
    if section is None:
        raise HTTPException(404, "bolum bulunamadi")
    suite = session.get(Suite, section.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)

    ids, frontier = [section_id], [section_id]
    while frontier:
        frontier = list(session.scalars(
            select(Section.id).where(Section.parent_id.in_(frontier))))
        ids.extend(frontier)

    now = datetime.now(timezone.utc)
    cases = session.scalars(
        select(Case).where(Case.section_id.in_(ids),
                           Case.is_deleted.is_(False))).all()
    for case in cases:
        case.is_deleted = True
        case.updated_by = user.id
        case.updated_on = now
        session.add(CaseHistory(
            case_id=case.id, user_id=user.id, created_on=now,
            changes=[{"field": "is_deleted", "old_text": "0", "new_text": "1"}],
            source="app"))

    held = session.scalar(
        select(func.count()).select_from(Case)
        .where(Case.section_id.in_(ids))) or 0
    if held:
        session.execute(Section.__table__.update()
                        .where(Section.id.in_(ids))
                        .values(is_deleted=True))
    else:
        session.execute(Section.__table__.delete().where(Section.id.in_(ids)))
    record(session, user, "delete", "section", section_id, label=section.name,
           project_id=suite.project_id if suite else None, request=request,
           detail={"sections": len(ids), "cases": len(cases)})
    session.commit()


@router.get("/suites/{suite_id}/sections", response_model=list[SectionNode])
def section_tree(suite_id: int, session: Session = Depends(get_session),
                 _: User = Depends(current_user)):
    """The whole tree in one call, with per-section case counts.

    One suite here holds 909 sections; fetching them level by level would mean
    hundreds of round trips just to draw the sidebar.
    """
    sections = session.scalars(
        select(Section).where(Section.suite_id == suite_id,
                              Section.is_deleted.is_(False))
        .order_by(Section.display_order)).all()

    counts = dict(session.execute(
        select(Case.section_id, func.count())
        .where(Case.suite_id == suite_id, Case.is_deleted.is_(False))
        .group_by(Case.section_id)).all())

    # Built field by field on purpose. model_validate() on the ORM object
    # would follow Section.children, so every node would arrive carrying its
    # whole subtree -- rendered twice on the client, and one lazy query per
    # section on the way out.
    nodes = {
        s.id: SectionNode(
            id=s.id, suite_id=s.suite_id, parent_id=s.parent_id, name=s.name,
            description=s.description, depth=s.depth,
            display_order=s.display_order, case_count=counts.get(s.id, 0),
            children=[],
        )
        for s in sections
    }

    roots = []
    for section in sections:
        node = nodes[section.id]
        parent = nodes.get(section.parent_id) if section.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


@router.get("/suites/{suite_id}/cases", response_model=CasePage)
def list_cases(suite_id: int,
               section_id: int | None = None,
               q: str | None = None,
               type_id: int | None = None,
               priority_id: int | None = None,
               created_by: int | None = None,
               field: str | None = None,
               value: str | None = None,
               sort: str = "section",
               include_deleted: bool = False,
               include_subsections: bool = True,
               offset: int = 0,
               limit: int = Query(100, le=500),
               session: Session = Depends(get_session),
               _: User = Depends(current_user)):
    """List cases with the filters a five-thousand-case suite makes necessary."""
    where = [Case.suite_id == suite_id]
    if section_id is not None:
        if include_subsections:
            # a folder means the folder and everything under it; selecting a
            # parent and seeing nothing is the usual complaint otherwise
            ids, frontier = {section_id}, [section_id]
            while frontier:
                children = session.scalars(
                    select(Section.id).where(Section.parent_id.in_(frontier))).all()
                children = [c for c in children if c not in ids]
                ids.update(children)
                frontier = children
            where.append(Case.section_id.in_(ids))
        else:
            where.append(Case.section_id == section_id)
    if not include_deleted:
        where.append(Case.is_deleted.is_(False))
    if q:
        where.append(Case.title.ilike(f"%{q}%"))
    if type_id is not None:
        where.append(Case.type_id == type_id)
    if priority_id is not None:
        where.append(Case.priority_id == priority_id)
    if created_by is not None:
        where.append(Case.created_by == created_by)
    if field and value:
        where.append(Case.custom[field].astext == value)

    order = {
        "section": (Case.section_id, Case.display_order),
        "title": (Case.title,),
        "updated": (Case.updated_on.desc().nulls_last(),),
        "id": (Case.id,),
    }.get(sort, (Case.section_id, Case.display_order))

    total = session.scalar(select(func.count()).select_from(Case).where(*where))
    rows = session.scalars(
        select(Case).where(*where).order_by(*order)
        .offset(offset).limit(limit)).all()
    return CasePage(total=total, offset=offset, limit=limit,
                    items=[CaseSummary.model_validate(r) for r in rows])


@router.get("/projects/{project_id}/cases")
def explore_cases(project_id: int,
                  q: str | None = None,
                  suite_id: int | None = None,
                  type_id: int | None = None,
                  priority_id: int | None = None,
                  refs: str | None = Query(None, pattern="^(with|without)$"),
                  executed: str | None = Query(None, pattern="^(yes|no)$"),
                  sort: str = Query("title", pattern="^(title|runs|updated|id)$"),
                  offset: int = 0,
                  limit: int = Query(100, le=500),
                  session: Session = Depends(get_session),
                  _: User = Depends(current_user)):
    """The case library across a whole project, filtered.

    Every number on the reports page was a dead end: you could read that a
    third of the library has never been run and had no way to see which
    third. Cases live under suites, so until now the only case list was
    suite-scoped and a project-wide answer did not exist as a screen.

    Each row carries how many runs it has appeared in, which is what makes
    "never run" and "run constantly" separable when deciding what to prune.
    """
    suite_ids = select(Suite.id).where(
        Suite.project_id == project_id).scalar_subquery()

    where = [Case.suite_id.in_(suite_ids), Case.is_deleted.is_(False)]
    if suite_id is not None:
        where.append(Case.suite_id == suite_id)
    if q:
        where.append(Case.title.ilike(f"%{q}%"))
    if type_id is not None:
        where.append(Case.type_id == type_id)
    if priority_id is not None:
        where.append(Case.priority_id == priority_id)
    if refs == "with":
        where.append(and_(Case.refs.is_not(None), Case.refs != ""))
    elif refs == "without":
        where.append(or_(Case.refs.is_(None), Case.refs == ""))

    # One grouped count over tests rather than a correlated subquery per row,
    # and scoped to this project's runs: aggregating all 1,064,011 test rows
    # to answer a question about one project's 4,468 cases cost 1.4s a page.
    runs = (select(Test.case_id, func.count(func.distinct(Test.run_id))
                   .label("runs"))
            .join(Run, Test.run_id == Run.id)
            .where(Run.project_id == project_id, Test.case_id.is_not(None))
            .group_by(Test.case_id).subquery())

    if executed == "yes":
        where.append(runs.c.runs > 0)
    elif executed == "no":
        where.append(runs.c.runs.is_(None))

    base = (select(Case, func.coalesce(runs.c.runs, 0).label("runs"),
                   Suite.name.label("suite_name"))
            .outerjoin(runs, runs.c.case_id == Case.id)
            .join(Suite, Case.suite_id == Suite.id)
            .where(*where))

    order = {
        "title": (Case.title,),
        "runs": (func.coalesce(runs.c.runs, 0).desc(), Case.id),
        "updated": (Case.updated_on.desc().nulls_last(),),
        "id": (Case.id,),
    }[sort]

    total = session.scalar(
        select(func.count()).select_from(base.subquery()))
    rows = session.execute(
        base.order_by(*order).offset(offset).limit(limit)).all()

    return {
        "total": total, "offset": offset, "limit": limit,
        "items": [{
            "id": case.id, "title": case.title,
            "suite_id": case.suite_id, "suite_name": suite_name,
            "section_id": case.section_id,
            "type_id": case.type_id, "priority_id": case.priority_id,
            "refs": case.refs, "updated_on": case.updated_on,
            "runs": run_count,
        } for case, run_count, suite_name in rows],
    }


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: int, session: Session = Depends(get_session),
             _: User = Depends(current_user)):
    case = session.scalar(
        select(Case).where(Case.id == case_id)
        .options(selectinload(Case.steps)))
    if case is None:
        raise HTTPException(404, "case bulunamadi")
    return _render_case(session, case)


def _write_steps(session: Session, case: Case, steps):
    """Replace a case's steps.

    The delete has to be issued and flushed before the inserts: steps are
    unique on (case_id, idx), and clearing the collection alone lets
    SQLAlchemy order the new rows ahead of the removals, which trips the
    constraint on any case whose step count did not shrink.
    """
    session.execute(
        CaseStep.__table__.delete().where(CaseStep.case_id == case.id))
    session.flush()
    # expired rather than cleared: clear() would queue a second delete for
    # rows the statement above already removed, which SQLAlchemy then warns
    # about at commit ("expected to delete 2 row(s); 0 were matched")
    session.expire(case, ["steps"])
    for idx, step in enumerate(steps):
        case.steps.append(CaseStep(
            idx=idx, content=step.content, expected=step.expected,
            additional_info=step.additional_info, refs=step.refs))


@router.post("/cases", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    section = session.get(Section, payload.section_id)
    if section is None:
        raise HTTPException(400, "section bulunamadi")
    suite = session.get(Suite, section.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)
    now = datetime.now(timezone.utc)
    case = Case(
        section_id=section.id, suite_id=section.suite_id, title=payload.title,
        template_id=payload.template_id, type_id=payload.type_id,
        priority_id=payload.priority_id, milestone_id=payload.milestone_id,
        refs=payload.refs, estimate=payload.estimate, custom=payload.custom,
        created_by=user.id, created_on=now, updated_by=user.id, updated_on=now,
    )
    session.add(case)
    session.flush()
    _write_steps(session, case, payload.steps)
    session.commit()
    session.refresh(case)
    return _render_case(session, case)


@router.patch("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: int, payload: CaseUpdate,
                session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    case = session.scalar(select(Case).where(Case.id == case_id)
                          .options(selectinload(Case.steps)))
    if case is None:
        raise HTTPException(404, "case bulunamadi")
    suite = session.get(Suite, case.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)

    changes = []
    data = payload.model_dump(exclude_unset=True)
    steps = data.pop("steps", None)
    custom = data.pop("custom", None)

    for field, value in data.items():
        before = getattr(case, field)
        if before != value:
            changes.append({"field": field, "old_text": str(before),
                            "new_text": str(value)})
            setattr(case, field, value)

    if custom is not None:
        # merge, never replace: the editor sends the fields it shows, and a
        # case carries fields the current project scope hides. Replacing the
        # dict would quietly delete them. An explicit null clears one.
        merged = dict(case.custom or {})
        for key, value in custom.items():
            before = merged.get(key)
            if before == value:
                continue
            # per-field entries, because "custom changed" tells a reviewer
            # nothing a year later
            changes.append({"field": key,
                            "old_text": "" if before is None else str(before),
                            "new_text": "" if value is None else str(value)})
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        case.custom = merged
    if steps is not None:
        changes.append({"field": "steps", "old_text": f"{len(case.steps)} adim",
                        "new_text": f"{len(steps)} adim"})
        _write_steps(session, case, payload.steps)

    if changes:
        case.updated_by = user.id
        case.updated_on = datetime.now(timezone.utc)
        # the same append-only log the TestRail history was imported into
        session.add(CaseHistory(case_id=case.id, user_id=user.id,
                                created_on=case.updated_on, changes=changes,
                                source="app"))
    session.commit()
    session.refresh(case)
    return _render_case(session, case)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: int, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    """Soft delete, matching TestRail's own is_deleted flag.

    Runs reference cases, and hard-deleting one would silently rewrite the
    history of every run it appears in.
    """
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "case bulunamadi")
    suite = session.get(Suite, case.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)
    if not case.is_deleted:
        case.is_deleted = True
        case.updated_by = user.id
        case.updated_on = datetime.now(timezone.utc)
        session.add(CaseHistory(
            case_id=case.id, user_id=user.id, created_on=case.updated_on,
            changes=[{"field": "is_deleted", "old_text": "0", "new_text": "1"}],
            source="app"))
        session.commit()


@router.get("/cases/{case_id}/history")
def case_history(case_id: int, session: Session = Depends(get_session),
                 _: User = Depends(current_user)):
    rows = session.scalars(
        select(CaseHistory).where(CaseHistory.case_id == case_id)
        .order_by(CaseHistory.created_on.desc())).all()
    return [{"id": r.id, "user_id": r.user_id, "created_on": r.created_on,
             "changes": r.changes, "source": r.source} for r in rows]
