"""Scheduled digests: what goes out, when, and what deliberately does not."""
from datetime import datetime, timedelta, timezone

import pytest

from app import digests


class Fake:
    """A subscription without touching the database, for the timing rules."""
    def __init__(self, **kw):
        self.is_active = True
        self.frequency = "daily"
        self.hour = 8
        self.weekday = 0
        self.last_sent_on = None
        self.__dict__.update(kw)


def at(hour, day=15, weekday_check=None):
    return datetime(2026, 6, day, hour, 0, tzinfo=timezone.utc)


def test_not_due_before_the_chosen_hour():
    assert not digests.is_due(Fake(hour=8), at(7))
    assert digests.is_due(Fake(hour=8), at(8))


def test_the_hour_is_a_floor_not_an_exact_match():
    """A container that was down at 08:00 should still deliver at 09:20."""
    assert digests.is_due(Fake(hour=8), at(9))
    assert digests.is_due(Fake(hour=8), at(23))


def test_only_once_a_day_however_often_the_scheduler_runs():
    sub = Fake(hour=8, last_sent_on=at(8))
    assert not digests.is_due(sub, at(9))
    assert not digests.is_due(sub, at(23))
    assert digests.is_due(sub, at(8, day=16))


def test_weekly_waits_for_its_day():
    monday = datetime(2026, 6, 15, 9, tzinfo=timezone.utc)
    assert monday.weekday() == 0
    assert digests.is_due(Fake(frequency="weekly", weekday=0), monday)
    assert not digests.is_due(Fake(frequency="weekly", weekday=2), monday)


def test_an_inactive_subscription_never_fires():
    assert not digests.is_due(Fake(is_active=False), at(12))


def test_a_missed_day_widens_the_window_rather_than_losing_it():
    """Measured from the last delivery, so a failed send is not a lost day."""
    sub = Fake(last_sent_on=at(8, day=13))
    since = digests._since(sub, at(8, day=15))
    assert (at(8, day=15) - since).days == 2


# ---- the digests themselves -------------------------------------------------

@pytest.fixture
def subscribe(app_client, admin):
    def _make(**body):
        response = app_client.post("/api/report-subscriptions", headers=admin,
                                   json=body)
        assert response.status_code == 201, response.text
        return response.json()
    return _make


def test_an_empty_digest_is_not_sent(app_client, admin, project, subscribe, db):
    """Nobody reads the fourth 'no failures' e-mail.

    Asserted on this subscription alone: dispatch reports totals across
    every subscription in the database, and other tests leave behind ones
    that do have something to say -- which is why this used to fail only
    when the whole suite ran."""
    from sqlalchemy import select

    from app.models import Notification, ReportSubscription

    sub = subscribe(kind="failures", project_id=project["id"])
    preview = app_client.post(
        f"/api/report-subscriptions/{sub['id']}/preview", headers=admin).json()
    assert preview["empty"] is True
    before = db.scalar(select(Notification.id).order_by(Notification.id.desc()).limit(1)) or 0

    result = app_client.post("/api/report-subscriptions/dispatch",
                             headers=admin).json()
    assert result["empty"] >= 1

    db.expire_all()
    row = db.get(ReportSubscription, sub["id"])
    # the window moved on, so the next digest does not re-report this period
    assert row.last_sent_on is not None
    # but nothing was written for it
    new = db.scalars(select(Notification).where(
        Notification.id > before, Notification.kind == "digest",
        Notification.user_id == row.user_id)).all()
    assert all(project["name"] not in n.body for n in new)


def test_failures_digest_names_the_tests(app_client, admin, project, suite,
                                         make_case, subscribe):
    make_case("Kırılan test")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Gece koşumu",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 5, "defects": "JIRA-42"})

    sub = subscribe(kind="failures", project_id=project["id"])
    preview = app_client.post(
        f"/api/report-subscriptions/{sub['id']}/preview", headers=admin).json()

    assert preview["empty"] is False
    assert "1 başarısız test" in preview["subject"]
    assert "Kırılan test" in preview["body"]
    assert "Gece koşumu" in preview["body"]
    assert "JIRA-42" in preview["body"]


def test_milestone_digest_separates_late_from_upcoming(app_client, admin,
                                                       project, subscribe):
    now = datetime.now(timezone.utc)
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Geciken sürüm",
                          "due_on": (now - timedelta(days=3)).isoformat()})
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Yaklaşan sürüm",
                          "due_on": (now + timedelta(days=2)).isoformat()})
    # outside the seven-day horizon: must not appear
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Uzaktaki sürüm",
                          "due_on": (now + timedelta(days=40)).isoformat()})

    sub = subscribe(kind="milestones", project_id=project["id"])
    preview = app_client.post(
        f"/api/report-subscriptions/{sub['id']}/preview", headers=admin).json()

    assert "gecikti" in preview["subject"]
    assert "Geciken sürüm" in preview["body"]
    assert "Yaklaşan sürüm" in preview["body"]
    assert "Uzaktaki sürüm" not in preview["body"]


def test_dispatch_delivers_and_does_not_repeat(app_client, admin, project,
                                               suite, make_case, subscribe):
    make_case("Tekrar etmeyen")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Koşum",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 5})

    subscribe(kind="failures", project_id=project["id"], hour=0)
    first = app_client.post("/api/report-subscriptions/dispatch",
                            headers=admin).json()
    assert first["sent"] >= 1

    inbox = app_client.get("/api/notifications", headers=admin).json()
    digest = next(n for n in inbox["items"] if n["kind"] == "digest")
    assert "başarısız" in digest["subject"]

    second = app_client.post("/api/report-subscriptions/dispatch",
                             headers=admin).json()
    assert second["sent"] == 0, "aynı gün ikinci kez gönderilmemeli"


def test_only_admins_can_dispatch(app_client, admin):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    tester = next(r for r in roles if r["name"] == "Tester")
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Digest testçi", "email": "digest@test.local",
        "password": "digest-parola-1", "role_id": tester["id"],
        "is_active": True})
    token = app_client.post("/api/auth/token", data={
        "username": "digest@test.local",
        "password": "digest-parola-1"}).json()["access_token"]

    response = app_client.post("/api/report-subscriptions/dispatch",
                               headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_subscriptions_are_private_to_their_owner(app_client, admin, subscribe):
    subscribe(kind="summary")
    token = app_client.post("/api/auth/token", data={
        "username": "digest@test.local",
        "password": "digest-parola-1"}).json()["access_token"]
    theirs = app_client.get("/api/report-subscriptions",
                            headers={"Authorization": f"Bearer {token}"}).json()
    assert theirs["items"] == []
