"""Test runs, the tests inside them and result entry."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ...audit import record
from ...db import get_session
from ...notifications import notify
from ...models import (Attachment, Case, CaseStep, Result, ResultStep, Run,
                       Status, Test, User)
from ..deps import current_user
from ..permissions import (WRITE_RESULTS, WRITE_RUNS, assert_can, assert_read,
                           assert_read_of)
from ..rendering import referenced_ids, rewrite_deep
from ..schemas import (CaseIds, ResultCreate, ResultOut, RunCreate, RunOut,
                       RunUpdate, TestOut, TestPage, TestPatch)

router = APIRouter(prefix="/api", tags=["runs"])


@router.get("/projects/{project_id}/runs", response_model=list[RunOut])
def list_runs(project_id: int,
              milestone_id: int | None = None,
              include_completed: bool = True,
              archived: bool = False,
              q: str | None = None,
              offset: int = 0,
              limit: int = Query(100, le=500),
              session: Session = Depends(get_session),
              user: User = Depends(current_user)):
    """Live runs by default.

    TestRail archives a run when a release is done, and there are seven
    archived runs here for every live one. Mixing them would make the page
    useless for the work actually in flight, so archived is a deliberate
    switch.
    """
    assert_read(session, user, project_id)
    where = [Run.project_id == project_id, Run.is_archived.is_(archived)]
    if milestone_id is not None:
        where.append(Run.milestone_id == milestone_id)
    if not include_completed:
        where.append(Run.is_completed.is_(False))
    if q:
        where.append(Run.name.ilike(f"%{q}%"))
    runs = session.scalars(
        select(Run).where(*where).order_by(Run.created_on.desc().nulls_last())
        .offset(offset).limit(limit)).all()
    if not runs:
        return []

    # progress per run in one grouped query rather than one per row
    ids = [r.id for r in runs]
    counts: dict[int, dict[str, int]] = {}
    for run_id, status_id, n in session.execute(
            select(Test.run_id, Test.status_id, func.count())
            .where(Test.run_id.in_(ids))
            .group_by(Test.run_id, Test.status_id)):
        slot = counts.setdefault(
            run_id, {"total": 0, "passed": 0, "failed": 0, "untested": 0})
        slot["total"] += n
        if status_id == 1:
            slot["passed"] += n
        elif status_id == 5:
            slot["failed"] += n
        elif status_id is None or status_id == 3:
            slot["untested"] += n

    out = []
    for run in runs:
        row = RunOut.model_validate(run)
        slot = counts.get(run.id, {})
        row.test_count = slot.get("total", 0)
        row.passed_count = slot.get("passed", 0)
        row.failed_count = slot.get("failed", 0)
        row.untested_count = slot.get("untested", 0)
        out.append(row)
    return out


@router.post("/projects/{project_id}/runs", response_model=RunOut,
             status_code=201)
def create_run(project_id: int, payload: RunCreate,
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    assert_can(session, user, WRITE_RUNS, project_id)
    """Create a run and populate it with tests.

    A test is a snapshot of the case at the moment the run is created, which
    is why the case fields are copied across rather than joined at read time:
    editing the case later must not rewrite what was executed.
    """
    run = Run(
        project_id=project_id, suite_id=payload.suite_id, name=payload.name,
        description=payload.description, milestone_id=payload.milestone_id,
        assignedto_id=payload.assignedto_id, refs=payload.refs,
        include_all=payload.include_all, created_by=user.id,
        created_on=datetime.now(timezone.utc), config_ids=[],
    )
    session.add(run)
    session.flush()

    where = [Case.suite_id == payload.suite_id, Case.is_deleted.is_(False)]
    if not payload.include_all:
        if payload.case_ids:
            where.append(Case.id.in_(payload.case_ids))
        elif payload.section_ids:
            where.append(Case.section_id.in_(payload.section_ids))
        else:
            where.append(Case.id.is_(None))  # nothing selected: an empty run
    cases = session.scalars(select(Case).where(*where)).all()

    session.add_all([
        Test(run_id=run.id, case_id=c.id, title=c.title, status_id=3,
             type_id=c.type_id, priority_id=c.priority_id,
             template_id=c.template_id, milestone_id=c.milestone_id,
             refs=c.refs, estimate=c.estimate, custom=dict(c.custom or {}),
             assignedto_id=payload.assignedto_id)
        for c in cases])

    if payload.assignedto_id and payload.assignedto_id != user.id:
        notify(session, payload.assignedto_id, "test_assigned",
               f"Size {len(cases)} test atandı: {run.name[:70]}",
               f"{user.name} '{run.name}' koşumunu size atadı.",
               link=f"/#/p/{project_id}/runs/{run.id}")
    session.commit()
    session.refresh(run)

    out = RunOut.model_validate(run)
    out.test_count = len(cases)
    out.untested_count = len(cases)
    return out


@router.patch("/runs/{run_id}", response_model=RunOut)
def update_run(run_id: int, payload: RunUpdate,
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RUNS, run.project_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_completed") and not run.completed_on:
        run.completed_on = datetime.now(timezone.utc)
    if data.get("is_completed") is False:
        run.completed_on = None
    for field, value in data.items():
        setattr(run, field, value)
    session.commit()
    session.refresh(run)
    return run


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, session: Session = Depends(get_session),
            user: User = Depends(current_user)):
    assert_read_of(session, user, run=run_id)
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    return run


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, request: Request,
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """Delete a run and everything recorded in it.

    This is a hard delete, as it was in TestRail: a run nobody wants is
    noise, and keeping a tombstone would leave the status roll-ups counting
    tests that no longer mean anything. Archived runs are refused -- those
    are the release records, and losing one loses the only account of what
    shipped.
    """
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RUNS, run.project_id)
    if run.is_archived:
        raise HTTPException(400, "arsivlenmis kosum silinemez")

    tests = list(session.scalars(select(Test.id).where(Test.run_id == run_id)))
    if tests:
        results = list(session.scalars(
            select(Result.id).where(Result.test_id.in_(tests))))
        # attachments hang off results by (entity_type, entity_id) rather than
        # a foreign key, so the database cascade does not reach them
        if results:
            session.execute(Attachment.__table__.delete().where(
                Attachment.entity_type == "result",
                Attachment.entity_id.in_(results)))
        # deleted at table level on purpose: the ORM's default cascade would
        # try to null tests.run_id, which the schema forbids, and the database
        # already cascades tests -> results -> result_steps
        session.execute(Test.__table__.delete().where(Test.run_id == run_id))
    record(session, user, "delete", "run", run_id, label=run.name,
           project_id=run.project_id, request=request,
           detail={"tests": len(tests)})
    session.delete(run)
    session.commit()


@router.post("/runs/{run_id}/tests", status_code=201)
def add_tests(run_id: int, payload: CaseIds,
              session: Session = Depends(get_session),
              user: User = Depends(current_user)):
    """Add cases to a run that already exists.

    A run built from a section misses anything written afterwards, and until
    now the only way to pick those up was to start a new run and lose the
    results already entered.
    """
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RUNS, run.project_id)
    if run.is_archived:
        raise HTTPException(400, "arsivlenmis kosum degistirilemez")

    present = set(session.scalars(
        select(Test.case_id).where(Test.run_id == run_id)))
    cases = session.scalars(
        select(Case).where(Case.id.in_(payload.case_ids),
                           Case.is_deleted.is_(False))).all()

    added = 0
    for case in cases:
        if case.id in present:
            continue
        session.add(Test(
            run_id=run_id, case_id=case.id, title=case.title, status_id=3,
            type_id=case.type_id, priority_id=case.priority_id,
            template_id=case.template_id, refs=case.refs,
            estimate=case.estimate, custom=dict(case.custom or {}),
            assignedto_id=run.assignedto_id))
        added += 1

    # a run that gained a hand-picked case is no longer "everything in the
    # suite", and saying otherwise would make the next sync re-add the rest
    if added and run.include_all:
        run.include_all = False
    session.commit()
    return {"added": added, "skipped": len(payload.case_ids) - added}


@router.delete("/runs/{run_id}/tests", status_code=200)
def remove_tests(run_id: int, payload: CaseIds,
                 session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    """Drop tests from a run, by test id."""
    run = session.get(Run, run_id)
    if run is None:
        raise HTTPException(404, "kosum bulunamadi")
    assert_can(session, user, WRITE_RUNS, run.project_id)
    if run.is_archived:
        raise HTTPException(400, "arsivlenmis kosum degistirilemez")

    tests = list(session.scalars(
        select(Test.id).where(Test.run_id == run_id,
                              Test.id.in_(payload.case_ids))))
    if tests:
        results = list(session.scalars(
            select(Result.id).where(Result.test_id.in_(tests))))
        if results:
            session.execute(Attachment.__table__.delete().where(
                Attachment.entity_type == "result",
                Attachment.entity_id.in_(results)))
        session.execute(Test.__table__.delete().where(Test.id.in_(tests)))
    if tests and run.include_all:
        run.include_all = False
    session.commit()
    return {"removed": len(tests)}


@router.delete("/results/{result_id}", status_code=204)
def delete_result(result_id: int, request: Request,
                  session: Session = Depends(get_session),
                  user: User = Depends(current_user)):
    """Remove one result and roll the test back to the previous one.

    TestRail never allowed this; a mis-click meant a wrong status stayed in
    the record for good. The test status is recomputed rather than left
    pointing at a result that is gone.
    """
    result = session.get(Result, result_id)
    if result is None:
        raise HTTPException(404, "sonuc bulunamadi")
    test = session.get(Test, result.test_id)
    run = session.get(Run, test.run_id) if test else None
    assert_can(session, user, WRITE_RESULTS, run.project_id if run else None)
    if run is not None and run.is_archived:
        raise HTTPException(400, "arsivlenmis kosumdan sonuc silinemez")

    session.execute(Attachment.__table__.delete().where(
        Attachment.entity_type == "result", Attachment.entity_id == result_id))
    record(session, user, "delete", "result", result_id,
           label=(test.title if test else None),
           project_id=run.project_id if run else None, request=request,
           detail={"status_id": result.status_id, "test_id": result.test_id})
    session.delete(result)
    session.flush()

    if test is not None:
        previous = session.scalar(
            select(Result).where(Result.test_id == test.id)
            .order_by(Result.created_on.desc()).limit(1))
        test.status_id = previous.status_id if previous else 3
    session.commit()


@router.get("/runs/{run_id}/summary")
def run_summary(run_id: int, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    """Status breakdown, computed rather than stored.

    TestRail keeps denormalised passed_count/failed_count columns on the run
    and they drift. One grouped count over 88k rows is fast enough.
    """
    assert_read_of(session, user, run=run_id)
    rows = session.execute(
        select(Test.status_id, func.count())
        .where(Test.run_id == run_id).group_by(Test.status_id)).all()
    return {"run_id": run_id,
            "by_status": {str(s) if s is not None else "untested": n
                          for s, n in rows},
            "total": sum(n for _, n in rows)}


@router.get("/runs/{run_id}/tests", response_model=TestPage)
def list_tests(run_id: int,
               status_id: int | None = None,
               assignedto_id: int | None = None,
               q: str | None = None,
               offset: int = 0,
               limit: int = Query(200, le=1000),
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """One page of a run's tests, with the real total.

    The biggest run here holds 10,062 tests. Returning a bare list meant the
    grid showed the first page and gave no sign there was more, and filtering
    in the browser could only ever filter what had already been fetched.
    """
    assert_read_of(session, user, run=run_id)
    where = [Test.run_id == run_id]
    if status_id is not None:
        where.append(Test.status_id == status_id)
    if assignedto_id is not None:
        where.append(Test.assignedto_id == assignedto_id)
    if q:
        where.append(Test.title.ilike(f"%{q}%"))

    total = session.scalar(
        select(func.count()).select_from(Test).where(*where)) or 0
    items = session.scalars(
        select(Test).where(*where).order_by(Test.id)
        .offset(offset).limit(limit)).all()
    return TestPage(total=total, offset=offset, limit=limit, items=items)


def _render_result(session: Session, result: Result) -> ResultOut:
    out = ResultOut.model_validate(result)
    out.attachments = [
        {"id": a.testrail_id, "filename": a.filename, "size": a.size,
         "content_type": a.content_type,
         "url": f"/api/attachments/{a.testrail_id}"}
        for a in session.scalars(
            select(Attachment).where(Attachment.entity_type == "result",
                                     Attachment.entity_id == result.id))]
    ids = referenced_ids(out.comment) | referenced_ids(out.custom)
    if ids:
        have = set(session.scalars(
            select(Attachment.testrail_id)
            .where(Attachment.testrail_id.in_(ids))))
        out.comment = rewrite_deep(out.comment, have)
        out.custom = rewrite_deep(out.custom, have)
    return out


@router.get("/tests/{test_id}")
def get_test(test_id: int, session: Session = Depends(get_session),
             user: User = Depends(current_user)):
    """A test with the case steps it was made from.

    The run grid used to show only a title, so a tester had to open the case
    in another tab to find out what to do. Steps come from the case; the
    latest per-step outcome comes from the most recent result.
    """
    assert_read_of(session, user, test=test_id)
    test = session.get(Test, test_id)
    if test is None:
        raise HTTPException(404, "test bulunamadi")

    steps = []
    if test.case_id:
        steps = [{"idx": s.idx, "content": s.content, "expected": s.expected,
                  "additional_info": s.additional_info}
                 for s in session.scalars(
                     select(CaseStep).where(CaseStep.case_id == test.case_id)
                     .order_by(CaseStep.idx))]

    latest = session.scalar(
        select(Result).where(Result.test_id == test_id)
        .options(selectinload(Result.step_results))
        .order_by(Result.created_on.desc()).limit(1))
    outcomes = {s.idx: s.status_id for s in (latest.step_results if latest else [])}

    run = session.get(Run, test.run_id)
    return {
        "id": test.id, "run_id": test.run_id, "case_id": test.case_id,
        "title": test.title, "status_id": test.status_id,
        "assignedto_id": test.assignedto_id, "refs": test.refs,
        "type_id": test.type_id, "priority_id": test.priority_id,
        "custom": test.custom,
        "is_archived": bool(run and run.is_archived),
        "steps": [{**s, "status_id": outcomes.get(s["idx"])} for s in steps],
    }


@router.patch("/tests/{test_id}", response_model=TestOut)
def update_test(test_id: int, payload: TestPatch,
                session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    """Reassign a single test.

    Assignment at run creation covers the bulk case; this covers the one
    where somebody picks up a colleague's test.
    """
    test = session.get(Test, test_id)
    if test is None:
        raise HTTPException(404, "test bulunamadi")
    run = session.get(Run, test.run_id)
    assert_can(session, user, WRITE_RESULTS, run.project_id if run else None)

    data = payload.model_dump(exclude_unset=True)
    previous = test.assignedto_id
    for key, value in data.items():
        setattr(test, key, value)

    if ("assignedto_id" in data and run is not None
            and test.assignedto_id not in (None, previous, user.id)):
        notify(session, test.assignedto_id, "test_assigned",
               f"Size bir test atandı: {test.title[:70]}",
               f"{user.name} '{test.title}' testini size atadı.",
               link=f"/#/p/{run.project_id}/runs/{run.id}/t/{test.id}")
    session.commit()
    session.refresh(test)
    return test


@router.get("/tests/{test_id}/results", response_model=list[ResultOut])
def list_results(test_id: int, session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    assert_read_of(session, user, test=test_id)
    rows = session.scalars(
        select(Result).where(Result.test_id == test_id)
        .options(selectinload(Result.step_results))
        .order_by(Result.created_on.desc())).all()
    return [_render_result(session, r) for r in rows]


@router.post("/tests/{test_id}/results", response_model=ResultOut,
             status_code=201)
def add_result(test_id: int, payload: ResultCreate,
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    test = session.get(Test, test_id)
    if test is None:
        raise HTTPException(404, "test bulunamadi")
    run = session.get(Run, test.run_id)
    assert_can(session, user, WRITE_RESULTS, run.project_id if run else None)
    if run is not None and run.is_archived:
        raise HTTPException(400, "arsivlenmis kosuma sonuc eklenemez")

    result = Result(
        test_id=test.id, status_id=payload.status_id, created_by=user.id,
        created_on=datetime.now(timezone.utc),
        assignedto_id=payload.assignedto_id, comment=payload.comment,
        version=payload.version, elapsed=payload.elapsed,
        defects=payload.defects, custom=payload.custom,
    )
    session.add(result)
    session.flush()

    for step in payload.step_results:
        session.add(ResultStep(
            result_id=result.id, idx=step.idx, content=step.content,
            expected=step.expected, actual=step.actual,
            status_id=step.status_id))

    # attachments are uploaded first and bound here, so a failed save never
    # leaves a file pointing at a result that does not exist
    if payload.attachment_ids:
        for row in session.scalars(
                select(Attachment).where(
                    Attachment.testrail_id.in_(payload.attachment_ids))):
            row.entity_type = "result"
            row.entity_id = result.id
    # the run grid reads the status off the test, so keep it in step
    test.status_id = payload.status_id

    # a failure on somebody else's test is the one event worth interrupting
    # them for; a pass is not
    status_name = next((s.name for s in session.scalars(select(Status))
                        if s.id == payload.status_id), "")
    if (test.assignedto_id and test.assignedto_id != user.id
            and status_name == "failed"):
        notify(session, test.assignedto_id, "result_failed",
               f"Testiniz başarısız: {test.title[:80]}",
               f"{user.name} sonucu 'Failed' olarak kaydetti."
               + (f"\n\n{payload.comment[:400]}" if payload.comment else ""),
               link=f"/#/p/{run.project_id}/runs/{run.id}/t/{test.id}")
    session.commit()
    session.refresh(result)
    return _render_result(session, result)
