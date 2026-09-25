"""Request throttling.

Two things this protects against, both of them real here rather than
theoretical:

Sign-in. The login endpoint is the one place an unauthenticated caller can
guess repeatedly, and bcrypt with a SHA-256 pre-hash is slow by design -- a
few hundred attempts a second would occupy the whole process, which is a
denial of service quite apart from the password guessing.

Automation. The result-posting endpoints are called from CI. A misconfigured
job in a retry loop can bury the database under writes, and the rest of the
team notices as "the app is slow" long before anyone finds the job.

Counted in memory, per process. This deployment runs a single API container,
so that is the whole picture; behind several workers each would keep its own
window and the effective limit would multiply. That is a deliberate trade --
a shared counter means Redis, and this is a twenty-person instance.
"""
import logging
import time
from collections import defaultdict, deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = logging.getLogger("ratelimit")

# Checked per request rather than captured at construction, because the
# middleware stack is built once at startup and the test suite has to be able
# to turn this on for two tests and off again for the other fifty.
ENABLED = True

# (method, path prefix) -> (requests, seconds)
RULES: list[tuple[str, str, int, int]] = [
    # a person mistyping their password does not reach ten in a minute
    ("POST", "/api/auth/token", 10, 60),
    # both answer an unauthenticated caller, and forgot sends mail
    ("POST", "/api/auth/forgot", 5, 300),
    ("POST", "/api/auth/set-password", 10, 60),
    # generous for a real CI run, tight enough to stop a runaway loop
    ("POST", "/api/results", 600, 60),
    ("POST", "/api/tests", 600, 60),
    ("POST", "/api/attachments", 120, 60),
    ("POST", "/api/suites", 30, 60),      # spreadsheet import
]

# whatever is left over, so one caller cannot monopolise the process
DEFAULT_LIMIT = (900, 60)


def _rule(method: str, path: str) -> tuple[int, int]:
    for rule_method, prefix, count, window in RULES:
        if method == rule_method and path.startswith(prefix):
            return count, window
    return DEFAULT_LIMIT


def _caller(request: Request) -> str:
    """Who to count against.

    The API token or the bearer token identifies a caller far better than an
    address does: every CI job behind one NAT shares an IP, and throttling
    one of them would throttle all of them.
    """
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return "t:" + auth[7:][-24:]
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return "ip:" + forwarded.split(",")[0].strip()
    return "ip:" + (request.client.host if request.client else "?")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if not ENABLED or request.method in ("GET", "HEAD", "OPTIONS"):
            return await call_next(request)

        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        limit, window = _rule(request.method, path)
        key = (_caller(request), f"{request.method} {_rule_key(path)}")
        now = time.monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > window:
            bucket.popleft()

        if len(bucket) >= limit:
            retry = int(window - (now - bucket[0])) + 1
            log.warning("limit asildi: %s %s (%s/%ss)", key[0], path, limit, window)
            # returned, not raised: middleware sits outside the router, so an
            # HTTPException raised here never reaches FastAPI's handler and
            # surfaces as a 500 instead
            return JSONResponse(
                {"detail": f"cok fazla istek, {retry} saniye sonra tekrar deneyin"},
                status_code=429, headers={"Retry-After": str(retry)})

        bucket.append(now)
        # keep the table from growing without bound on a long-running process
        if len(self.hits) > 10_000:
            self._sweep(now)
        return await call_next(request)

    def _sweep(self, now: float) -> None:
        stale = [k for k, v in self.hits.items() if not v or now - v[-1] > 3600]
        for key in stale:
            del self.hits[key]


def _rule_key(path: str) -> str:
    """Group a path so that ids do not each get their own bucket.

    /api/tests/9236740/results and /api/tests/9236741/results are the same
    endpoint being hammered, and counting them separately would defeat the
    limit entirely.
    """
    parts = [p for p in path.split("/") if p]
    return "/".join(p for p in parts if not p.isdigit())[:60]
