"""Recording administrative changes.

One call, deliberately cheap and deliberately forgiving: an audit write must
never be the reason a legitimate action fails. If the row cannot be written
the action still goes through and the failure is logged.

Case edits are not recorded here -- they have their own history table, which
the migration filled with 152,872 rows and which the case page renders.
"""
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy.orm import Session

from .models import AuditEntry, User

log = logging.getLogger("audit")


def record(session: Session, user: User | None, action: str, entity_type: str,
           entity_id: int | str | None = None, *, label: str | None = None,
           project_id: int | None = None, detail: dict | None = None,
           request: Request | None = None) -> None:
    """Add one line to the audit log.

    The caller commits: the entry belongs to the same transaction as the
    change it describes, so a rolled-back delete leaves no trace of having
    happened.
    """
    try:
        session.add(AuditEntry(
            created_on=datetime.now(timezone.utc),
            user_id=user.id if user else None,
            action=action,
            entity_type=entity_type,
            entity_id=None if entity_id is None else str(entity_id),
            label=(label or "")[:255] or None,
            project_id=project_id,
            detail=detail or {},
            ip=_client_ip(request),
        ))
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("denetim kaydi yazilamadi: %s", exc)


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    # behind the bundled nginx, the real address is in X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host[:45] if request.client else None
