"""Jira lookups, without touching Jira: a fake session stands in for it."""
import pytest


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


def issue(key, status="Done", category="done"):
    return {"key": key, "fields": {
        "summary": f"{key} başlığı", "issuetype": {"name": "Bug"},
        "status": {"name": status, "statusCategory": {"key": category}}}}


class FakeJira:
    """Knows PM-1 and PM-2; rejects any search that names an unknown key,
    exactly as Jira does."""
    known = {"PM-1": issue("PM-1"), "PM-2": issue("PM-2", "In Progress", "indeterminate")}

    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, json, timeout):
        self.calls.append(("search", json["jql"]))
        keys = json["jql"][len("key in ("):-1].split(", ")
        if any(k not in self.known for k in keys):
            return FakeResponse(400, {"errorMessages": ["An issue with key does not exist"]})
        return FakeResponse(200, {"issues": [self.known[k] for k in keys]})

    def get(self, url, params, timeout):
        key = url.rsplit("/", 1)[1]
        self.calls.append(("issue", key))
        return FakeResponse(200, self.known[key]) if key in self.known else FakeResponse(404, {})


@pytest.fixture
def fake_jira(monkeypatch):
    from app import jira
    from app.config import get_settings

    fake = FakeJira()
    settings = get_settings()
    monkeypatch.setattr(settings, "jira_base_url", "https://ornek.atlassian.net")
    monkeypatch.setattr(settings, "jira_email", "bot@ornek.test")
    monkeypatch.setattr(settings, "jira_api_token", "gizli-token")
    monkeypatch.setattr(jira, "_session", lambda: fake)
    jira._cache.clear()
    yield fake
    jira._cache.clear()


def test_keys_are_recognised_and_nothing_else():
    from app import jira
    assert jira.keys_in("PM-3766, TK-1493 ve PM-3766; abc-1, X-1, 2024-05") == ["PM-3766", "TK-1493"]


def test_one_unknown_key_does_not_hide_the_others(fake_jira):
    from app import jira
    found = jira.lookup(["PM-1", "PM-2", "NOPE-9"])
    assert found["PM-1"]["status"] == "Done" and found["PM-1"]["missing"] is False
    assert found["PM-2"]["category"] == "indeterminate"
    assert found["NOPE-9"]["missing"] is True
    assert found["PM-1"]["url"] == "https://ornek.atlassian.net/browse/PM-1"
    # the rejected batch fell back to one request per key
    assert ("issue", "NOPE-9") in fake_jira.calls


def test_answers_are_cached(fake_jira):
    from app import jira
    jira.lookup(["PM-1"])
    before = len(fake_jira.calls)
    jira.lookup(["PM-1"])
    assert len(fake_jira.calls) == before


def test_nothing_is_asked_when_jira_is_not_configured(monkeypatch):
    from app import jira
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "jira_api_token", "")
    monkeypatch.setattr(jira, "_session", lambda: pytest.fail("Jira was called"))
    jira._cache.clear()
    assert jira.lookup(["PM-1"]) == {}


def test_endpoints_need_a_login_and_never_return_the_token(app_client, admin, fake_jira):
    # a fresh client: the shared one carries the session cookie of every
    # earlier sign-in in the suite
    from starlette.testclient import TestClient
    assert TestClient(app_client.app).get("/api/jira/config").status_code == 401
    assert TestClient(app_client.app).get("/api/jira/issues?keys=PM-1").status_code == 401
    config = app_client.get("/api/jira/config", headers=admin).json()
    assert config == {"enabled": True, "base_url": "https://ornek.atlassian.net"}
    assert "gizli-token" not in str(config)

    found = app_client.get("/api/jira/issues?keys=PM-1,<script>,PM-2",
                           headers=admin).json()
    assert set(found) == {"PM-1", "PM-2"}      # the non-key never reached Jira
