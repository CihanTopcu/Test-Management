"""Saved filters, notifications, shared steps and case copy/move."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ...db import get_session
from ...models import (Case, CaseStep, Notification, NotificationPreference,
                       SavedFilter, Section, SharedStep, Suite, User)
from ...notifications import KINDS, send_pending
from ..deps import current_user
from ..permissions import WRITE_CASES, assert_can, capabilities

router = APIRouter(prefix="/api", tags=["workspace"])


# --- saved filters ----------------------------------------------------------

class FilterIn(BaseModel):
    name: str
    project_id: int
    suite_id: int | None = None
    criteria: dict = Field(default_factory=dict)
    is_shared: bool = False


@router.get("/filters")
def list_filters(project_id: int, session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    rows = session.scalars(
        select(SavedFilter)
        .where(SavedFilter.project_id == project_id,
               or_(SavedFilter.owner_id == user.id,
                   SavedFilter.is_shared.is_(True)))
        .order_by(SavedFilter.name)).all()
    return [{"id": f.id, "name": f.name, "suite_id": f.suite_id,
             "criteria": f.criteria, "is_shared": f.is_shared,
             "mine": f.owner_id == user.id} for f in rows]


@router.post("/filters", status_code=201)
def save_filter(payload: FilterIn, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    existing = session.scalar(
        select(SavedFilter).where(SavedFilter.owner_id == user.id,
                                  SavedFilter.project_id == payload.project_id,
                                  SavedFilter.name == payload.name))
    row = existing or SavedFilter(owner_id=user.id,
                                  project_id=payload.project_id,
                                  name=payload.name)
    row.suite_id = payload.suite_id
    row.criteria = payload.criteria
    row.is_shared = payload.is_shared
    session.add(row)
    session.commit()
    return {"id": row.id, "name": row.name}


@router.delete("/filters/{filter_id}", status_code=204)
def delete_filter(filter_id: int, session: Session = Depends(get_session),
                  user: User = Depends(current_user)):
    row = session.get(SavedFilter, filter_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "filtre bulunamadi")
    session.delete(row)
    session.commit()


# --- notifications ----------------------------------------------------------

@router.get("/notifications")
def list_notifications(unread_only: bool = False, limit: int = 50,
                       session: Session = Depends(get_session),
                       user: User = Depends(current_user)):
    where = [Notification.user_id == user.id]
    if unread_only:
        where.append(Notification.is_read.is_(False))
    rows = session.scalars(
        select(Notification).where(*where)
        .order_by(Notification.created_at.desc()).limit(limit)).all()
    unread = session.scalar(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id,
               Notification.is_read.is_(False)))
    return {"unread": unread, "items": [{
        "id": n.id, "kind": n.kind, "subject": n.subject, "body": n.body,
        "link": n.link, "is_read": n.is_read, "created_at": n.created_at,
        "email_status": n.email_status,
    } for n in rows]}


@router.post("/notifications/read", status_code=204)
def mark_read(ids: list[int] | None = None,
              session: Session = Depends(get_session),
              user: User = Depends(current_user)):
    where = [Notification.user_id == user.id, Notification.is_read.is_(False)]
    if ids:
        where.append(Notification.id.in_(ids))
    for row in session.scalars(select(Notification).where(*where)):
        row.is_read = True
    session.commit()


@router.get("/notifications/preferences")
def get_preferences(session: Session = Depends(get_session),
                    user: User = Depends(current_user)):
    saved = {p.kind: p for p in session.scalars(
        select(NotificationPreference)
        .where(NotificationPreference.user_id == user.id))}
    return [{"kind": kind, "label": label,
             "in_app": saved[kind].in_app if kind in saved else True,
             "email": saved[kind].email if kind in saved else False}
            for kind, label in KINDS.items()]


class PreferenceIn(BaseModel):
    kind: str
    in_app: bool = True
    email: bool = False


@router.put("/notifications/preferences")
def set_preference(payload: PreferenceIn,
                   session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    if payload.kind not in KINDS:
        raise HTTPException(400, "bilinmeyen bildirim turu")
    row = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.kind == payload.kind))
    if row is None:
        row = NotificationPreference(user_id=user.id, kind=payload.kind)
        session.add(row)
    row.in_app = payload.in_app
    row.email = payload.email
    session.commit()
    return {"kind": row.kind, "in_app": row.in_app, "email": row.email}


@router.post("/notifications/flush")
def flush(session: Session = Depends(get_session),
          user: User = Depends(current_user)):
    """Deliver queued e-mail now. Normally a scheduled job calls this."""
    if "admin" not in capabilities(session, user):
        raise HTTPException(403, "bu islem icin yonetici yetkisi gerekli")
    return send_pending(session)


# --- shared steps -----------------------------------------------------------

class SharedStepIn(BaseModel):
    title: str
    steps: list[dict] = Field(default_factory=list)


@router.get("/projects/{project_id}/shared-steps")
def list_shared_steps(project_id: int, session: Session = Depends(get_session),
                      _: User = Depends(current_user)):
    rows = session.scalars(
        select(SharedStep).where(SharedStep.project_id == project_id)
        .order_by(SharedStep.title)).all()
    # how many cases reference each one, so nobody edits a block used in 400
    # places without knowing
    usage = dict(session.execute(
        select(CaseStep.shared_step_id, func.count(func.distinct(CaseStep.case_id)))
        .where(CaseStep.shared_step_id.in_([r.id for r in rows]))
        .group_by(CaseStep.shared_step_id)).all()) if rows else {}
    return [{"id": r.id, "title": r.title, "steps": r.steps,
             "step_count": len(r.steps or []), "used_by": usage.get(r.id, 0),
             "created_on": r.created_on, "updated_on": r.updated_on}
            for r in rows]


@router.post("/projects/{project_id}/shared-steps", status_code=201)
def create_shared_step(project_id: int, payload: SharedStepIn,
                       session: Session = Depends(get_session),
                       user: User = Depends(current_user)):
    assert_can(session, user, WRITE_CASES, project_id)
    now = datetime.now(timezone.utc)
    row = SharedStep(project_id=project_id, title=payload.title,
                     steps=payload.steps, created_by=user.id, created_on=now,
                     updated_by=user.id, updated_on=now)
    session.add(row)
    session.commit()
    return {"id": row.id, "title": row.title}


@router.patch("/shared-steps/{step_id}")
def update_shared_step(step_id: int, payload: SharedStepIn,
                       session: Session = Depends(get_session),
                       user: User = Depends(current_user)):
    row = session.get(SharedStep, step_id)
    if row is None:
        raise HTTPException(404, "paylasilan adim bulunamadi")
    assert_can(session, user, WRITE_CASES, row.project_id)
    row.title = payload.title
    row.steps = payload.steps
    row.updated_by = user.id
    row.updated_on = datetime.now(timezone.utc)
    session.commit()
    return {"id": row.id, "title": row.title}


# --- copy / move ------------------------------------------------------------

class MoveIn(BaseModel):
    case_ids: list[int] = Field(min_length=1)
    section_id: int


@router.post("/cases/bulk-move")
def move_cases(payload: MoveIn, session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """Move cases to another section, possibly in another suite."""
    target = session.get(Section, payload.section_id)
    if target is None:
        raise HTTPException(400, "hedef bolum bulunamadi")
    suite = session.get(Suite, target.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)

    cases = session.scalars(
        select(Case).where(Case.id.in_(payload.case_ids))).all()
    now = datetime.now(timezone.utc)
    for case in cases:
        case.section_id = target.id
        case.suite_id = target.suite_id
        case.updated_by = user.id
        case.updated_on = now
    session.commit()
    return {"moved": len(cases), "section_id": target.id,
            "suite_id": target.suite_id}


@router.post("/cases/bulk-copy")
def copy_cases(payload: MoveIn, session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """Duplicate cases into another section, steps and custom fields included."""
    target = session.get(Section, payload.section_id)
    if target is None:
        raise HTTPException(400, "hedef bolum bulunamadi")
    suite = session.get(Suite, target.suite_id)
    assert_can(session, user, WRITE_CASES, suite.project_id if suite else None)

    sources = session.scalars(
        select(Case).where(Case.id.in_(payload.case_ids))
        .options(selectinload(Case.steps))).all()
    now = datetime.now(timezone.utc)
    made = []
    for source in sources:
        copy = Case(
            section_id=target.id, suite_id=target.suite_id,
            title=source.title, template_id=source.template_id,
            type_id=source.type_id, priority_id=source.priority_id,
            milestone_id=source.milestone_id, refs=source.refs,
            estimate=source.estimate, custom=dict(source.custom or {}),
            display_order=source.display_order,
            created_by=user.id, created_on=now,
            updated_by=user.id, updated_on=now,
        )
        for step in source.steps:
            copy.steps.append(CaseStep(
                idx=step.idx, content=step.content, expected=step.expected,
                additional_info=step.additional_info, refs=step.refs,
                shared_step_id=step.shared_step_id))
        session.add(copy)
        made.append(copy)
    session.commit()
    return {"copied": len(made), "ids": [c.id for c in made],
            "section_id": target.id}
