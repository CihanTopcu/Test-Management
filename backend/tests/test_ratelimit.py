"""Request throttling.

The limiter is off for the rest of the suite -- fifty tests drive the same
endpoints far harder than a person would -- so these switch it on around
themselves and clear the counters afterwards.
"""
import pytest

from app import ratelimit
from app.ratelimit import _caller, _rule, _rule_key


def test_paths_group_by_endpoint_not_by_id():
    """Otherwise every test id gets its own bucket and nothing is limited."""
    assert _rule_key("/api/tests/9236740/results") == _rule_key(
        "/api/tests/9236741/results")
    assert _rule_key("/api/tests/1/results") == "api/tests/results"


def test_login_is_the_tightest_rule():
    assert _rule("POST", "/api/auth/token") == (10, 60)
    assert _rule("POST", "/api/cases") == (900, 60)


def test_token_identifies_the_caller_before_the_address():
    """CI jobs share a NAT address; throttling one would throttle all."""
    class Tokened:
        headers = {"authorization": "Bearer tm_abcdefghijklmnopqrstuvwxyz"}
        client = None
    assert _caller(Tokened()).startswith("t:")

    class Anon:
        headers = {"x-forwarded-for": "10.0.0.7, 172.16.0.1"}
        client = None
    assert _caller(Anon()) == "ip:10.0.0.7"


@pytest.fixture
def limiter(app_client):
    """Turn the limiter on for one test, and leave no counters behind."""
    ratelimit.ENABLED = True
    for middleware in _instances(app_client.app):
        middleware.hits.clear()
    yield
    ratelimit.ENABLED = False
    for middleware in _instances(app_client.app):
        middleware.hits.clear()


def _instances(app):
    """Walk the built middleware stack for our own layer."""
    found, node = [], getattr(app, "middleware_stack", None)
    while node is not None:
        if isinstance(node, ratelimit.RateLimitMiddleware):
            found.append(node)
        node = getattr(node, "app", None)
    return found


def test_repeated_failed_logins_are_refused(app_client, limiter):
    codes = [app_client.post("/api/auth/token", data={
        "username": "yok@test.local", "password": "yanlış"}).status_code
        for _ in range(12)]

    assert codes[0] == 401, "ilk deneme normal sekilde reddedilmeli"
    assert 429 in codes, "tekrar eden denemeler sinirlanmali"
    assert codes.index(429) == 10, "sinir on denemeden sonra devreye girmeli"

    refused = app_client.post("/api/auth/token", data={
        "username": "yok@test.local", "password": "yanlış"})
    assert refused.status_code == 429
    assert refused.headers["Retry-After"].isdigit()
    assert "cok fazla istek" in refused.json()["detail"]


def test_reading_is_never_throttled(app_client, limiter):
    """A page that draws twenty widgets must not throttle itself."""
    codes = {app_client.get("/api/health").status_code for _ in range(60)}
    assert codes == {200}


def test_a_successful_login_still_works_after_a_few_misses(app_client, limiter):
    for _ in range(3):
        app_client.post("/api/auth/token", data={
            "username": "admin@test.local", "password": "yanlış"})
    ok = app_client.post("/api/auth/token", data={
        "username": "admin@test.local", "password": "test-parola-123"})
    assert ok.status_code == 200
