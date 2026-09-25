"""Projects, milestones and the configurable vocabularies."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...audit import record
from ...db import get_session
from pydantic import BaseModel

from ...models import (CaseType, CustomField, CustomFieldOption, Group,
                       Milestone, Priority, Project, ProjectGroup,
                       ProjectMember, Role, Status, Template, User)
from ..deps import current_user
from ..permissions import (MANAGE_PROJECT, assert_can, assert_may_grant,
                           assert_read, capabilities, readable_project_ids)
from ..schemas import (CatalogOut, CustomFieldOut, MilestoneCreate,
                       MilestoneOut, MilestoneUpdate, ProjectOut, UserOut)

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session),
                  user: User = Depends(current_user)):
    """The projects this user may open -- not every project there is."""
    query = select(Project).order_by(Project.name)
    readable = readable_project_ids(session, user)
    if readable is not None:
        query = query.where(Project.id.in_(readable))
    return session.scalars(query).all()


class ProjectIn(BaseModel):
    name: str
    announcement: str | None = None
    show_announcement: bool = False
    suite_mode: int = 3
    # chosen up front, so a confidential project is never open for a moment
    default_role_id: int | None = None


class ProjectPatch(BaseModel):
    name: str | None = None
    announcement: str | None = None
    show_announcement: bool | None = None
    is_completed: bool | None = None
    # sent as null to go back to "global role"; omitted to leave it alone
    default_role_id: int | None = None


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectIn, session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    """Create a project.

    Guarded by the admin capability rather than manage_project: a project is
    a container other people get added to, not something a team lead spins up
    per sprint.
    """
    if "admin" not in capabilities(session, user):
        raise HTTPException(403, "proje olusturmak icin yonetici yetkisi gerekli")
    if session.scalar(select(Project).where(Project.name == payload.name)):
        raise HTTPException(400, "bu isimde bir proje zaten var")

    if payload.default_role_id is not None and session.get(Role, payload.default_role_id) is None:
        raise HTTPException(400, "rol bulunamadi")
    project = Project(**payload.model_dump())
    session.add(project)
    session.flush()
    # the creator has to be a member, or they cannot see what they just made
    session.add(ProjectMember(project_id=project.id, user_id=user.id,
                              role_id=user.role_id))
    session.commit()
    session.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectPatch,
                   session: Session = Depends(get_session),
                   user: User = Depends(current_user)):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "proje bulunamadi")
    assert_can(session, user, MANAGE_PROJECT, project_id)
    data = payload.model_dump(exclude_unset=True)
    if "default_role_id" in data:
        assert_may_grant(session, user, project_id, data["default_role_id"])
        record(session, user, "update", "project_access", project_id,
               label=project.name, project_id=project_id,
               detail={"default_role_id": data["default_role_id"],
                       "before": project.default_role_id})
    if data.get("is_completed") and not project.completed_on:
        project.completed_on = datetime.now(timezone.utc)
    if data.get("is_completed") is False:
        project.completed_on = None
    for key, value in data.items():
        setattr(project, key, value)
    session.commit()
    session.refresh(project)
    return project


# --- project membership -----------------------------------------------------

class MemberIn(BaseModel):
    user_id: int
    role_id: int | None = None


@router.get("/projects/{project_id}/members")
def list_members(project_id: int, session: Session = Depends(get_session),
                 user: User = Depends(current_user)):
    assert_read(session, user, project_id)
    rows = session.execute(
        select(ProjectMember, User.name, User.email)
        .join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(User.name)).all()
    return [{"user_id": m.user_id, "role_id": m.role_id,
             "name": name, "email": email} for m, name, email in rows]


@router.put("/projects/{project_id}/members")
def set_member(project_id: int, payload: MemberIn, request: Request,
               session: Session = Depends(get_session),
               user: User = Depends(current_user)):
    """Add somebody to a project, or change the role they hold in it.

    A project role overrides the global one, which is how a person can lead
    one product and only read another.
    """
    assert_can(session, user, MANAGE_PROJECT, project_id)
    assert_may_grant(session, user, project_id, payload.role_id)
    row = session.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id,
                                    ProjectMember.user_id == payload.user_id))
    if row is None:
        row = ProjectMember(project_id=project_id, user_id=payload.user_id)
        session.add(row)
    row.role_id = payload.role_id
    record(session, user, "update", "project_member", payload.user_id,
           project_id=project_id, request=request,
           detail={"role_id": payload.role_id})
    session.commit()
    return {"user_id": payload.user_id, "role_id": payload.role_id}


@router.delete("/projects/{project_id}/members/{user_id}", status_code=204)
def remove_member(project_id: int, user_id: int, request: Request,
                  session: Session = Depends(get_session),
                  user: User = Depends(current_user)):
    assert_can(session, user, MANAGE_PROJECT, project_id)
    row = session.scalar(
        select(ProjectMember).where(ProjectMember.project_id == project_id,
                                    ProjectMember.user_id == user_id))
    if row is not None:
        record(session, user, "delete", "project_member", user_id,
               project_id=project_id, request=request)
        session.delete(row)
        session.commit()


# --- group access -----------------------------------------------------------

class GroupAccessIn(BaseModel):
    group_id: int
    role_id: int


@router.get("/projects/{project_id}/groups")
def list_group_access(project_id: int, session: Session = Depends(get_session),
                      user: User = Depends(current_user)):
    """Groups holding a role in this project, as TestRail's Access tab
    lists them under the individual users."""
    assert_read(session, user, project_id)
    rows = session.execute(
        select(ProjectGroup, Group.name)
        .join(Group, Group.id == ProjectGroup.group_id)
        .where(ProjectGroup.project_id == project_id)
        .order_by(Group.name)).all()
    return [{"group_id": g.group_id, "role_id": g.role_id, "name": name}
            for g, name in rows]


@router.put("/projects/{project_id}/groups")
def set_group_access(project_id: int, payload: GroupAccessIn, request: Request,
                     session: Session = Depends(get_session),
                     user: User = Depends(current_user)):
    assert_can(session, user, MANAGE_PROJECT, project_id)
    assert_may_grant(session, user, project_id, payload.role_id)
    if session.get(Group, payload.group_id) is None:
        raise HTTPException(404, "grup bulunamadi")
    if session.get(Role, payload.role_id) is None:
        raise HTTPException(400, "rol bulunamadi")
    row = session.scalar(
        select(ProjectGroup).where(ProjectGroup.project_id == project_id,
                                   ProjectGroup.group_id == payload.group_id))
    if row is None:
        row = ProjectGroup(project_id=project_id, group_id=payload.group_id,
                           role_id=payload.role_id)
        session.add(row)
    row.role_id = payload.role_id
    record(session, user, "update", "project_group", payload.group_id,
           project_id=project_id, request=request,
           detail={"role_id": payload.role_id})
    session.commit()
    return {"group_id": payload.group_id, "role_id": payload.role_id}


@router.delete("/projects/{project_id}/groups/{group_id}", status_code=204)
def remove_group_access(project_id: int, group_id: int, request: Request,
                        session: Session = Depends(get_session),
                        user: User = Depends(current_user)):
    assert_can(session, user, MANAGE_PROJECT, project_id)
    row = session.scalar(
        select(ProjectGroup).where(ProjectGroup.project_id == project_id,
                                   ProjectGroup.group_id == group_id))
    if row is not None:
        record(session, user, "delete", "project_group", group_id,
               project_id=project_id, request=request)
        session.delete(row)
        session.commit()


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, session: Session = Depends(get_session),
                user: User = Depends(current_user)):
    assert_read(session, user, project_id)
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "proje bulunamadi")
    return project


@router.get("/projects/{project_id}/milestones",
            response_model=list[MilestoneOut])
def list_milestones(project_id: int, session: Session = Depends(get_session),
                    user: User = Depends(current_user)):
    assert_read(session, user, project_id)
    return session.scalars(
        select(Milestone)
        .where(Milestone.project_id == project_id)
        .order_by(Milestone.parent_id.nulls_first(), Milestone.name)
    ).all()


@router.post("/projects/{project_id}/milestones", response_model=MilestoneOut,
             status_code=201)
def create_milestone(project_id: int, payload: MilestoneCreate,
                     session: Session = Depends(get_session),
                     user: User = Depends(current_user)):
    assert_can(session, user, MANAGE_PROJECT, project_id)
    if session.get(Project, project_id) is None:
        raise HTTPException(404, "proje bulunamadi")
    milestone = Milestone(project_id=project_id, **payload.model_dump())
    session.add(milestone)
    session.commit()
    session.refresh(milestone)
    return milestone


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
def update_milestone(milestone_id: int, payload: MilestoneUpdate,
                     session: Session = Depends(get_session),
                     user: User = Depends(current_user)):
    milestone = session.get(Milestone, milestone_id)
    if milestone is None:
        raise HTTPException(404, "milestone bulunamadi")
    assert_can(session, user, MANAGE_PROJECT, milestone.project_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("is_completed") and not milestone.completed_on:
        milestone.completed_on = datetime.now(timezone.utc)
    if data.get("is_completed") is False:
        milestone.completed_on = None
    for field, value in data.items():
        setattr(milestone, field, value)
    session.commit()
    session.refresh(milestone)
    return milestone


@router.delete("/milestones/{milestone_id}", status_code=204)
def delete_milestone(milestone_id: int, request: Request,
                     session: Session = Depends(get_session),
                     user: User = Depends(current_user)):
    """Delete a milestone; runs and plans that used it keep their history.

    The foreign keys are ON DELETE SET NULL, so a run simply stops being
    attached to a milestone rather than disappearing with it. Sub-milestones
    are re-parented to the milestone's own parent for the same reason.
    """
    milestone = session.get(Milestone, milestone_id)
    if milestone is None:
        raise HTTPException(404, "milestone bulunamadi")
    assert_can(session, user, MANAGE_PROJECT, milestone.project_id)

    for child in session.scalars(
            select(Milestone).where(Milestone.parent_id == milestone_id)):
        child.parent_id = milestone.parent_id
    record(session, user, "delete", "milestone", milestone_id,
           label=milestone.name, project_id=milestone.project_id,
           request=request)
    session.delete(milestone)
    session.commit()


@router.get("/users", response_model=list[UserOut])
def list_users(session: Session = Depends(get_session),
               _: User = Depends(current_user)):
    return session.scalars(select(User).order_by(User.name)).all()


@router.get("/catalog", response_model=CatalogOut)
def get_catalog(session: Session = Depends(get_session),
                _: User = Depends(current_user)):
    """One call for everything a case form needs to render.

    The UI would otherwise fetch six lookup tables before it can draw a single
    dropdown, and these rows change about twice a year.
    """
    fields = session.scalars(
        select(CustomField).order_by(CustomField.display_order)).all()
    options: dict[str, list[dict]] = {}
    for opt in session.scalars(
            select(CustomFieldOption).order_by(CustomFieldOption.display_order)):
        field = next((f for f in fields if f.id == opt.field_id), None)
        if field is not None:
            options.setdefault(field.system_name, []).append(
                {"value": opt.value, "label": opt.label})

    def rows(model, *cols):
        return [{c: getattr(r, c) for c in cols}
                for r in session.scalars(select(model))]

    return CatalogOut(
        case_types=rows(CaseType, "id", "name", "is_default"),
        priorities=rows(Priority, "id", "name", "short_name", "priority_level"),
        statuses=rows(Status, "id", "name", "label", "color", "is_untested"),
        templates=rows(Template, "id", "name", "is_default"),
        case_fields=[CustomFieldOut.model_validate(f) for f in fields
                     if f.entity == "case"],
        result_fields=[CustomFieldOut.model_validate(f) for f in fields
                       if f.entity == "result"],
        field_options=options,
    )
