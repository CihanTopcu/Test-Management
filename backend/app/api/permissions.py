"""Role enforcement.

The roles came across from TestRail as names only -- Admin, Lead, Tester,
Designer, Corebanking Tester, Read-only, No Access -- with nothing attached to
them. What each one may do is a policy decision, so it lives in a table
(roles.permissions) rather than in code, seeded from the defaults below and
editable afterwards.

Scope matters as much as the verb: somebody can be a Lead in TRANSIT and
Read-only in COREBANKING. capabilities() below spells out how the role that
applies in a project is chosen.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (Case, GroupMember, Plan, Project, ProjectGroup,
                      ProjectMember, Result, Role, Run, Section, Suite, Test,
                      User)
from .deps import current_user

# capabilities, coarse on purpose: finer grain invites a permission matrix
# nobody can reason about
READ = "read"
WRITE_CASES = "write_cases"
WRITE_RUNS = "write_runs"
WRITE_RESULTS = "write_results"
MANAGE_PROJECT = "manage_project"
ADMIN = "admin"

ALL = [READ, WRITE_CASES, WRITE_RUNS, WRITE_RESULTS, MANAGE_PROJECT, ADMIN]

DEFAULTS: dict[str, list[str]] = {
    "admin": ALL,
    "lead": [READ, WRITE_CASES, WRITE_RUNS, WRITE_RESULTS, MANAGE_PROJECT],
    "designer": [READ, WRITE_CASES],
    "tester": [READ, WRITE_RUNS, WRITE_RESULTS],
    "corebanking tester": [READ, WRITE_RUNS, WRITE_RESULTS],
    "read-only": [READ],
    "no access": [],
}


def default_for(role_name: str) -> list[str]:
    return DEFAULTS.get(role_name.strip().lower(), [READ])


def _role_capabilities(role: Role | None) -> set[str]:
    if role is None:
        return {READ}
    granted = role.permissions.get("capabilities") if role.permissions else None
    if not granted:
        granted = default_for(role.name)
    return set(granted)


def _global(session: Session, user: User) -> set[str]:
    return _role_capabilities(
        session.get(Role, user.role_id) if user.role_id else None)


def capabilities(session: Session, user: User,
                 project_id: int | None = None) -> set[str]:
    """What this user may do, in this project if one is named.

    TestRail's order, which is what the people moving over already know:

      1. an administrator may do everything, everywhere
      2. a membership of their own in the project
      3. otherwise the groups they belong to there, capabilities added up
      4. otherwise the project's default access
      5. otherwise their global role

    Until this was written out, only 2 and 5 existed and reading was never
    checked at all: a "No Access" account could open every project.
    """
    base = _global(session, user)
    if ADMIN in base:
        return set(ALL)
    if project_id is None:
        return base

    member_role = session.scalar(
        select(ProjectMember.role_id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id))
    if member_role:
        return _role_capabilities(session.get(Role, member_role))

    group_roles = session.scalars(
        select(ProjectGroup.role_id)
        .join(GroupMember, GroupMember.group_id == ProjectGroup.group_id)
        .where(ProjectGroup.project_id == project_id,
               GroupMember.user_id == user.id)).all()
    if group_roles:
        caps: set[str] = set()
        for role_id in set(group_roles):
            caps |= _role_capabilities(session.get(Role, role_id))
        return caps

    default_role = session.scalar(
        select(Project.default_role_id).where(Project.id == project_id))
    if default_role:
        return _role_capabilities(session.get(Role, default_role))
    return base


def readable_project_ids(session: Session, user: User) -> set[int] | None:
    """Every project this user may open, or None for "all of them".

    Worked out for all projects in a handful of queries rather than by
    calling capabilities() sixteen times, because every list in the
    application -- projects, dashboard, search, today -- starts here.
    """
    base = _global(session, user)
    if ADMIN in base:
        return None

    roles = {r.id: _role_capabilities(r) for r in session.scalars(select(Role))}
    own = dict(session.execute(
        select(ProjectMember.project_id, ProjectMember.role_id)
        .where(ProjectMember.user_id == user.id)).all())
    via_groups: dict[int, set[str]] = {}
    for project_id, role_id in session.execute(
            select(ProjectGroup.project_id, ProjectGroup.role_id)
            .join(GroupMember, GroupMember.group_id == ProjectGroup.group_id)
            .where(GroupMember.user_id == user.id)):
        via_groups.setdefault(project_id, set()).update(roles.get(role_id, set()))

    readable = set()
    for project_id, default_role in session.execute(
            select(Project.id, Project.default_role_id)):
        if project_id in own and own[project_id]:
            caps = roles.get(own[project_id], set())
        elif project_id in via_groups:
            caps = via_groups[project_id]
        elif default_role:
            caps = roles.get(default_role, set())
        else:
            caps = base
        if READ in caps:
            readable.add(project_id)
    return readable


def assert_read(session: Session, user: User, project_id: int | None) -> None:
    """404 rather than 403 for a project the user may not see: a closed
    project should not even confirm that it exists."""
    if project_id is None or READ not in capabilities(session, user, project_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "bulunamadi")


def project_of(session: Session, *, suite: int | None = None,
               section: int | None = None, case: int | None = None,
               run: int | None = None, test: int | None = None,
               plan: int | None = None, result: int | None = None) -> int | None:
    """The project a thing belongs to, for routes addressed by its own id."""
    if result is not None:
        test = session.scalar(select(Result.test_id).where(Result.id == result))
    if test is not None:
        run = session.scalar(select(Test.run_id).where(Test.id == test))
    if run is not None:
        return session.scalar(select(Run.project_id).where(Run.id == run))
    if plan is not None:
        return session.scalar(select(Plan.project_id).where(Plan.id == plan))
    if case is not None:
        suite = session.scalar(select(Case.suite_id).where(Case.id == case))
    if section is not None:
        suite = session.scalar(select(Section.suite_id).where(Section.id == section))
    if suite is not None:
        return session.scalar(select(Suite.project_id).where(Suite.id == suite))
    return None


def assert_read_of(session: Session, user: User, **ids: int | None) -> int:
    """assert_read for a route that only knows a suite, run, test… id.
    Returns the project, which the route usually wants next anyway."""
    project_id = project_of(session, **ids)
    assert_read(session, user, project_id)
    return project_id  # type: ignore[return-value]


def require(capability: str, project_param: str = "project_id"):
    """Dependency factory: require a capability, scoped to a path project.

    Used as ``Depends(require(WRITE_CASES))`` on a route that has a
    ``project_id`` path parameter; on routes without one the check falls back
    to the user's global role.
    """
    def dependency(request_project_id: int | None = None,
                   user: User = Depends(current_user),
                   session: Session = Depends(get_session)) -> User:
        allowed = capabilities(session, user, request_project_id)
        if capability not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"bu islem icin yetkiniz yok ({capability})")
        return user

    dependency.__name__ = f"require_{capability}"
    return dependency


def assert_can(session: Session, user: User, capability: str,
               project_id: int | None = None) -> None:
    """Imperative form, for routes that only learn the project after a lookup."""
    if capability not in capabilities(session, user, project_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"bu islem icin yetkiniz yok ({capability})")


def read_project(project_id: int, user: User = Depends(current_user),
                 session: Session = Depends(get_session)) -> None:
    """Router-level guard for everything mounted under a project's path.
    Put on a router, it covers routes added to it later without anyone
    having to remember."""
    assert_read(session, user, project_id)


def assert_may_grant(session: Session, user: User, project_id: int,
                     role_id: int | None) -> None:
    """Nobody hands out more than they hold.

    manage_project is what lets a lead add people to their project; without
    this it also let them make anyone -- themselves included -- an Admin
    there. An administrator may grant anything.
    """
    if role_id is None:
        return
    mine = capabilities(session, user, project_id)
    if ADMIN in mine:
        return
    role = session.get(Role, role_id)
    if role is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "rol bulunamadi")
    beyond = _role_capabilities(role) - mine
    if beyond:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "kendi yetkinizden fazlasini veremezsiniz: " + ", ".join(sorted(beyond)))
