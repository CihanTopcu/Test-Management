"""Role enforcement.

The roles came across from TestRail as names only -- Admin, Lead, Tester,
Designer, Corebanking Tester, Read-only, No Access -- with nothing attached to
them. What each one may do is a policy decision, so it lives in a table
(roles.permissions) rather than in code, seeded from the defaults below and
editable afterwards.

Scope matters as much as the verb: a project membership row can carry its own
role, so somebody can be a Lead in TRANSIT and Read-only in COREBANKING. The
project role wins where one exists, and the global role applies otherwise.
"""
from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ProjectMember, Role, User
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


def capabilities(session: Session, user: User,
                 project_id: int | None = None) -> set[str]:
    """What this user may do, in this project if one is named."""
    role_id = user.role_id
    if project_id is not None:
        member_role = session.scalar(
            select(ProjectMember.role_id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id))
        if member_role:
            role_id = member_role

    role = session.get(Role, role_id) if role_id else None
    if role is None:
        return {READ}
    granted = role.permissions.get("capabilities") if role.permissions else None
    if not granted:
        granted = default_for(role.name)
    return set(granted)


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
