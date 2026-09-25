"""Administration: users, roles and the custom-field registry.

Roles came across from TestRail as rows, but nothing enforced them yet. The
check here is deliberately simple -- the role named Admin can administer --
because a finer permission model is a decision for the team, not something to
invent while porting data.
"""
import os
from datetime import datetime, timedelta, timezone

from fastapi import (APIRouter, Depends, HTTPException, Query, Request,
                     status)
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...audit import record
from ...db import get_session
from ...models import (AuditEntry, CaseType, CustomField, CustomFieldOption,
                       Priority, Project, Role, Status, SyncRun, User)
from ...security import hash_password
from ..deps import current_user
from ..permissions import ALL as ALL_CAPABILITIES
from ..permissions import default_for
from ..schemas import (CustomFieldCreate, CustomFieldOut, CustomFieldUpdate,
                       UserAdminOut, UserCreate, UserUpdate)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(user: User = Depends(current_user),
                  session: Session = Depends(get_session)) -> User:
    role = session.get(Role, user.role_id) if user.role_id else None
    if role is None or role.name.strip().lower() != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "bu islem icin yonetici yetkisi gerekli")
    return user


@router.get("/users", response_model=list[UserAdminOut])
def list_users(session: Session = Depends(get_session),
               _: User = Depends(require_admin)):
    rows = session.scalars(select(User).order_by(User.name)).all()
    out = []
    for u in rows:
        item = UserAdminOut.model_validate(u)
        item.has_password = bool(u.password_hash)
        out.append(item)
    return out


@router.post("/users", response_model=UserAdminOut, status_code=201)
def create_user(payload: UserCreate, request: Request,
                session: Session = Depends(get_session),
                admin: User = Depends(require_admin)):
    if session.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(400, "bu e-posta zaten kayitli")
    user = User(name=payload.name, email=payload.email,
                role_id=payload.role_id, is_active=payload.is_active,
                password_hash=hash_password(payload.password)
                if payload.password else None)
    session.add(user)
    session.flush()
    record(session, admin, "create", "user", user.id, label=user.email,
           request=request, detail={"role_id": user.role_id})
    session.commit()
    session.refresh(user)
    item = UserAdminOut.model_validate(user)
    item.has_password = bool(user.password_hash)
    return item


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(user_id: int, payload: UserUpdate, request: Request,
                session: Session = Depends(get_session),
                admin: User = Depends(require_admin)):
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "kullanici bulunamadi")
    data = payload.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if data.get("is_active") is False and user.id == admin.id:
        raise HTTPException(400, "kendi hesabinizi pasife alamazsiniz")
    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.password_hash = hash_password(password)
    # the new password never reaches the log, only the fact that it changed
    record(session, admin, "update", "user", user.id, label=user.email,
           request=request,
           detail={**{k: v for k, v in data.items()},
                   **({"password": "changed"} if password else {})})
    session.commit()
    session.refresh(user)
    item = UserAdminOut.model_validate(user)
    item.has_password = bool(user.password_hash)
    return item


@router.get("/roles")
def list_roles(session: Session = Depends(get_session),
               _: User = Depends(require_admin)):
    """Roles with what each one may actually do.

    The names came from TestRail; the capabilities did not, so a role with
    nothing stored falls back to a sensible default that an admin can then
    change here.
    """
    rows = session.scalars(select(Role).order_by(Role.name)).all()
    return {
        "capabilities": ALL_CAPABILITIES,
        "roles": [{
            "id": r.id, "name": r.name, "is_default": r.is_default,
            "is_project_default": r.is_project_default,
            "capabilities": (r.permissions or {}).get("capabilities")
                            or default_for(r.name),
            "customised": bool((r.permissions or {}).get("capabilities")),
        } for r in rows],
    }


class RoleUpdate(BaseModel):
    capabilities: list[str]


@router.patch("/roles/{role_id}")
def update_role(role_id: int, payload: RoleUpdate, request: Request,
                session: Session = Depends(get_session),
                admin: User = Depends(require_admin)):
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(404, "rol bulunamadi")
    unknown = [c for c in payload.capabilities if c not in ALL_CAPABILITIES]
    if unknown:
        raise HTTPException(400, f"bilinmeyen yetki: {', '.join(unknown)}")
    before = (role.permissions or {}).get("capabilities", [])
    role.permissions = {**(role.permissions or {}),
                        "capabilities": payload.capabilities}
    # a role's capabilities reach every user who holds it, so the before and
    # after both go in the line
    record(session, admin, "update", "role", role.id, label=role.name,
           request=request, detail={"before": before,
                                    "after": payload.capabilities})
    session.commit()
    return {"id": role.id, "name": role.name,
            "capabilities": payload.capabilities}


# --- custom fields ----------------------------------------------------------

def _serialise(field: CustomField, session: Session) -> CustomFieldOut:
    out = CustomFieldOut.model_validate(field)
    return out


@router.get("/fields", response_model=list[CustomFieldOut])
def list_fields(session: Session = Depends(get_session),
                _: User = Depends(require_admin)):
    return session.scalars(
        select(CustomField).order_by(CustomField.entity,
                                     CustomField.display_order)).all()


def _write_options(session: Session, field: CustomField, options: list[dict]):
    """Rewrite a dropdown's choices, and mirror them into the field config so
    the catalog endpoint keeps serving one shape."""
    session.query(CustomFieldOption).filter(
        CustomFieldOption.field_id == field.id).delete()
    rows = []
    for order, opt in enumerate(options):
        value = opt.get("value")
        label = (opt.get("label") or "").strip()
        if value is None or not label:
            continue
        rows.append({"field_id": field.id, "value": int(value),
                     "label": label, "display_order": order})
    if rows:
        session.execute(CustomFieldOption.__table__.insert(), rows)
    items = "\n".join(f"{r['value']}, {r['label']}" for r in rows)
    configs = field.configs or []
    if not configs:
        configs = [{"context": {"is_global": field.is_global,
                                "project_ids": []}, "options": {}}]
    configs[0].setdefault("options", {})["items"] = items
    field.configs = list(configs)


@router.post("/fields", response_model=CustomFieldOut, status_code=201)
def create_field(payload: CustomFieldCreate,
                 session: Session = Depends(get_session),
                 _: User = Depends(require_admin)):
    name = payload.system_name.strip()
    if not name.startswith("custom_"):
        name = "custom_" + name
    exists = session.scalar(
        select(CustomField).where(CustomField.entity == payload.entity,
                                  CustomField.system_name == name))
    if exists:
        raise HTTPException(400, "bu sistem adi zaten kullaniliyor")

    order = session.scalar(
        select(func.coalesce(func.max(CustomField.display_order), 0))) or 0
    field = CustomField(
        entity=payload.entity, system_name=name, label=payload.label,
        description=payload.description, field_type=payload.field_type,
        is_global=payload.is_global, display_order=order + 1,
        configs=[{"context": {"is_global": payload.is_global,
                              "project_ids": payload.project_ids},
                  "options": {}}],
    )
    session.add(field)
    session.flush()
    if payload.options:
        _write_options(session, field, payload.options)
    session.commit()
    session.refresh(field)
    return _serialise(field, session)


@router.patch("/fields/{field_id}", response_model=CustomFieldOut)
def update_field(field_id: int, payload: CustomFieldUpdate,
                 session: Session = Depends(get_session),
                 _: User = Depends(require_admin)):
    field = session.get(CustomField, field_id)
    if field is None:
        raise HTTPException(404, "alan bulunamadi")
    data = payload.model_dump(exclude_unset=True)
    options = data.pop("options", None)
    project_ids = data.pop("project_ids", None)
    for key, value in data.items():
        setattr(field, key, value)

    if project_ids is not None or "is_global" in data:
        configs = list(field.configs or [{"context": {}, "options": {}}])
        ctx = dict(configs[0].get("context") or {})
        if project_ids is not None:
            ctx["project_ids"] = project_ids
        if "is_global" in data:
            ctx["is_global"] = data["is_global"]
        configs[0] = {**configs[0], "context": ctx}
        field.configs = configs

    if options is not None:
        _write_options(session, field, options)
    session.commit()
    session.refresh(field)
    return _serialise(field, session)


@router.get("/summary")
def admin_summary(session: Session = Depends(get_session),
                  _: User = Depends(require_admin)):
    """Counts for the administration landing page."""
    def count(model):
        return session.scalar(select(func.count()).select_from(model))

    return {
        "users": count(User),
        "active_users": session.scalar(
            select(func.count()).select_from(User).where(User.is_active.is_(True))),
        "roles": count(Role),
        "projects": count(Project),
        "case_fields": session.scalar(
            select(func.count()).select_from(CustomField)
            .where(CustomField.entity == "case")),
        "result_fields": session.scalar(
            select(func.count()).select_from(CustomField)
            .where(CustomField.entity == "result")),
        "case_types": count(CaseType),
        "priorities": count(Priority),
        "statuses": count(Status),
    }


@router.get("/audit")
def audit_log(action: str | None = None,
              entity_type: str | None = None,
              user_id: int | None = None,
              project_id: int | None = None,
              days: int = 90,
              offset: int = 0,
              limit: int = Query(100, le=500),
              session: Session = Depends(get_session),
              _: User = Depends(require_admin)):
    """Administrative changes, newest first.

    Restricted to admins: the log names who deleted what, which is exactly
    the kind of thing that should not be casually browsable.
    """
    since = datetime.now(timezone.utc) - timedelta(days=max(days, 1))
    where = [AuditEntry.created_on >= since]
    if action:
        where.append(AuditEntry.action == action)
    if entity_type:
        where.append(AuditEntry.entity_type == entity_type)
    if user_id:
        where.append(AuditEntry.user_id == user_id)
    if project_id:
        where.append(AuditEntry.project_id == project_id)

    total = session.scalar(
        select(func.count()).select_from(AuditEntry).where(*where)) or 0
    rows = session.scalars(
        select(AuditEntry).where(*where)
        .order_by(AuditEntry.created_on.desc())
        .offset(offset).limit(limit)).all()

    names = dict(session.execute(select(User.id, User.name)).all())
    projects = dict(session.execute(select(Project.id, Project.name)).all())
    return {
        "total": total, "offset": offset, "limit": limit,
        "items": [{
            "id": r.id, "created_on": r.created_on,
            "user_id": r.user_id, "user_name": names.get(r.user_id),
            "action": r.action, "entity_type": r.entity_type,
            "entity_id": r.entity_id, "label": r.label,
            "project_id": r.project_id,
            "project_name": projects.get(r.project_id),
            "detail": r.detail, "ip": r.ip,
        } for r in rows],
    }


# A manual request that nothing has picked up in this long is reported as
# such: the sync service is probably not running, and a "queued" that sits
# there forever looks exactly like one that is about to start.
QUEUE_PATIENCE = timedelta(minutes=2)


@router.get("/sync")
def sync_status(session: Session = Depends(get_session),
                _: User = Depends(require_admin)):
    """What the TestRail sync has been doing.

    A job nobody can see is a job nobody notices has stopped, which during a
    cut-over is the worst possible failure: both systems drift apart quietly
    and it only surfaces when TestRail is already gone. So the last runs are
    on the admin page, and a sync that is overdue says so.
    """
    runs = session.scalars(
        select(SyncRun).order_by(SyncRun.started_on.desc()).limit(20)).all()
    last_ok = session.scalar(
        select(SyncRun).where(SyncRun.status == "ok")
        .order_by(SyncRun.finished_on.desc()).limit(1))

    now = datetime.now(timezone.utc)
    interval = int(os.environ.get("TESTRAIL_SYNC_INTERVAL", 7 * 24 * 3600))
    enabled = os.environ.get("TESTRAIL_SYNC_ENABLED", "false").lower() not in (
        "0", "false", "no", "off", "")

    overdue = None
    if enabled and last_ok is not None and last_ok.finished_on is not None:
        finished = last_ok.finished_on
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        # one interval is normal, two means something stopped
        elapsed = (now - finished).total_seconds()
        overdue = elapsed > interval * 2

    # a manual request the sync service has not picked up in a while
    stalled = False
    queued = next((r for r in runs if r.status == "queued"), None)
    if queued is not None:
        asked = queued.started_on
        if asked.tzinfo is None:
            asked = asked.replace(tzinfo=timezone.utc)
        stalled = now - asked > QUEUE_PATIENCE

    return {
        "enabled": enabled,
        "interval_hours": round(interval / 3600),
        "overdue": overdue,
        "stalled": stalled,
        "last_ok": last_ok.finished_on if last_ok else None,
        "runs": [{
            "id": r.id,
            "started_on": r.started_on,
            "finished_on": r.finished_on,
            "status": r.status,
            "window_from": r.window_from,
            "trigger": r.trigger,
            "counts": r.counts or {},
            "error": r.error,
        } for r in runs],
    }


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def request_sync(request: Request, session: Session = Depends(get_session),
                 admin: User = Depends(require_admin)):
    """Ask for a sync now instead of at the next scheduled pass.

    The API does not run the sync itself: that lives in the separate sync
    service, which carries the TestRail client and can take many minutes.
    This only writes a queued row; the service polls for one between its
    scheduled passes and takes it, so the one-at-a-time rule and the
    window-only-moves-on-success rule stay in one place (migration/sync.py).
    """
    if os.environ.get("TESTRAIL_SYNC_ENABLED", "false").lower() in (
            "0", "false", "no", "off", ""):
        # the sync service skips every pass while switched off, so a queued
        # request would never be taken
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "TestRail esitlemesi kapali (TESTRAIL_SYNC_ENABLED)")

    busy = session.scalar(
        select(SyncRun).where(SyncRun.status.in_(("queued", "running")))
        .order_by(SyncRun.started_on.desc()).limit(1))
    if busy is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "zaten sirada ya da calisan bir esitleme var")

    run = SyncRun(started_on=datetime.now(timezone.utc), status="queued",
                  trigger="manual", counts={})
    session.add(run)
    session.flush()
    record(session, admin, "create", "sync", run.id,
           label="TestRail esitlemesi istendi", request=request)
    session.commit()
    return {"id": run.id, "status": run.status}


@router.delete("/sync/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_sync(run_id: int, request: Request,
                session: Session = Depends(get_session),
                admin: User = Depends(require_admin)):
    """Withdraw a request that has not started. A running pass is left alone:
    stopping it half-way would leave a partly loaded window."""
    run = session.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "esitleme bulunamadi")
    if run.status != "queued":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "yalnizca siradaki bir istek iptal edilebilir")
    run.status = "cancelled"
    run.finished_on = datetime.now(timezone.utc)
    record(session, admin, "delete", "sync", run.id,
           label="TestRail esitlemesi iptal edildi", request=request)
    session.commit()
