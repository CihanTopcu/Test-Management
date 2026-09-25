"""Reading issue status from Jira, for the keys people already write.

Cases carry references (TK-1493) and results carry defects (PM-3766), and
until now both were plain text: finding out whether PM-3766 was fixed meant
copying it into Jira by hand. This looks them up -- read only, through the
server, so the API token never reaches a browser.

Two things it is careful about:

  One bad key poisons a JQL search: "key in (A-1, B-2)" is rejected whole
  if either does not exist or cannot be seen with this token. A failed
  batch falls back to asking for each key on its own, so the rest still
  resolve and the bad one is reported as missing.

  Every page of the app would otherwise hit Jira. Answers are kept for ten
  minutes, missing keys included, per process.
"""
import logging
import re
import time

import requests

from .config import get_settings

log = logging.getLogger("jira")

# PROJECT-123: an upper-case project key of two to ten, a number
KEY = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{1,7})\b")
TTL = 600
BATCH = 50
FIELDS = ["summary", "status", "issuetype"]

_cache: dict[str, tuple[float, dict]] = {}


def enabled() -> bool:
    s = get_settings()
    return bool(s.jira_base_url and s.jira_email and s.jira_api_token)


def keys_in(text: str | None) -> list[str]:
    return list(dict.fromkeys(KEY.findall(text or "")))


def _url(key: str) -> str:
    return f"{get_settings().jira_base_url.rstrip('/')}/browse/{key}"


def _shape(issue: dict) -> dict:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    return {
        "key": issue["key"],
        "url": _url(issue["key"]),
        "summary": fields.get("summary"),
        "status": status.get("name"),
        # new | indeterminate | done -- Jira's own three buckets
        "category": (status.get("statusCategory") or {}).get("key"),
        "type": (fields.get("issuetype") or {}).get("name"),
        "missing": False,
    }


def _missing(key: str) -> dict:
    return {"key": key, "url": _url(key), "summary": None, "status": None,
            "category": None, "type": None, "missing": True}


def _session() -> requests.Session:
    s = get_settings()
    session = requests.Session()
    session.auth = (s.jira_email, s.jira_api_token)
    session.headers["Accept"] = "application/json"
    return session


def _fetch(keys: list[str]) -> dict[str, dict]:
    base = get_settings().jira_base_url.rstrip("/")
    out: dict[str, dict] = {}
    with _session() as http:
        for i in range(0, len(keys), BATCH):
            chunk = keys[i:i + BATCH]
            try:
                r = http.post(f"{base}/rest/api/3/search/jql", timeout=20, json={
                    "jql": f"key in ({', '.join(chunk)})",
                    "fields": FIELDS, "maxResults": len(chunk)})
            except requests.RequestException as exc:
                log.warning("jira erisilemedi: %s", exc)
                return out       # nothing cached: try again on the next request
            if r.ok:
                for issue in r.json().get("issues", []):
                    out[issue["key"]] = _shape(issue)
                # a key renamed by a project move comes back under its new
                # name; the old one is still worth a link
                for key in chunk:
                    out.setdefault(key, _missing(key))
                continue
            # one unknown key rejects the whole search: ask one by one
            for key in chunk:
                try:
                    one = http.get(f"{base}/rest/api/3/issue/{key}", timeout=20,
                                   params={"fields": ",".join(FIELDS)})
                except requests.RequestException:
                    continue
                out[key] = _shape(one.json()) if one.ok else _missing(key)
    return out


def lookup(keys: list[str]) -> dict[str, dict]:
    """Issue details for these keys, from cache where fresh."""
    now = time.time()
    wanted = [k for k in dict.fromkeys(keys) if KEY.fullmatch(k)]
    stale = [k for k in wanted if k not in _cache or now - _cache[k][0] > TTL]
    if stale and enabled():
        for key, data in _fetch(stale).items():
            _cache[key] = (now, data)
    return {k: _cache[k][1] for k in wanted if k in _cache}
