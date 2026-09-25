"""Jira issue status for the keys cases and results already mention."""
from fastapi import APIRouter, Depends, Query

from ... import jira
from ...config import get_settings
from ...models import User
from ..deps import current_user

router = APIRouter(prefix="/api/jira", tags=["jira"])


@router.get("/config")
def jira_config(_: User = Depends(current_user)):
    """Whether to draw keys as links, and where they point. The token
    stays on the server."""
    return {"enabled": jira.enabled(),
            "base_url": get_settings().jira_base_url.rstrip("/") or None}


@router.get("/issues")
def jira_issues(keys: str = Query(..., max_length=4000),
                _: User = Depends(current_user)):
    """Status and summary for up to 200 comma-separated issue keys (a full
    page of the case explorer); Jira is asked fifty at a time.
    Anything that is not shaped like a key is ignored, not sent on."""
    wanted = jira.keys_in(keys.replace(",", " "))[:200]
    return jira.lookup(wanted)
