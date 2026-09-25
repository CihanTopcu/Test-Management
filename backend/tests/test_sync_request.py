"""Asking for a TestRail sync from the admin page.

The API only queues the request; migration/sync.py takes it. Both halves
are tested here, because a queue nobody reads is the failure that matters.
"""
import os
import sys

import pytest
from sqlalchemy import delete

from app.models import SyncRun

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "..", "migration")


@pytest.fixture
def sync_on(monkeypatch, db):
    monkeypatch.setenv("TESTRAIL_SYNC_ENABLED", "true")
    db.execute(delete(SyncRun))
    db.commit()
    yield
    db.execute(delete(SyncRun))
    db.commit()


def test_request_is_queued_once(app_client, admin, sync_on):
    first = app_client.post("/api/admin/sync", headers=admin)
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"

    # a second press while the first is waiting must not stack up passes
    second = app_client.post("/api/admin/sync", headers=admin)
    assert second.status_code == 409

    status = app_client.get("/api/admin/sync", headers=admin).json()
    assert status["runs"][0]["status"] == "queued"
    assert status["runs"][0]["trigger"] == "manual"
    assert status["stalled"] is False


def test_queued_request_can_be_withdrawn(app_client, admin, sync_on):
    run_id = app_client.post("/api/admin/sync", headers=admin).json()["id"]

    assert app_client.delete(f"/api/admin/sync/{run_id}",
                             headers=admin).status_code == 204
    status = app_client.get("/api/admin/sync", headers=admin).json()
    assert status["runs"][0]["status"] == "cancelled"
    # and the button works again
    assert app_client.post("/api/admin/sync", headers=admin).status_code == 202


def test_running_pass_cannot_be_cancelled(app_client, admin, sync_on, db):
    run_id = app_client.post("/api/admin/sync", headers=admin).json()["id"]
    db.get(SyncRun, run_id).status = "running"
    db.commit()

    assert app_client.delete(f"/api/admin/sync/{run_id}",
                             headers=admin).status_code == 409


def test_refused_while_sync_is_switched_off(app_client, admin, monkeypatch):
    monkeypatch.setenv("TESTRAIL_SYNC_ENABLED", "false")
    assert app_client.post("/api/admin/sync", headers=admin).status_code == 409


def test_only_admins_can_ask(app_client, admin, sync_on):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    read_only = next(r for r in roles if r["name"] == "Read-only")
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Eşitleme okuyucu", "email": "esitleme-okur@test.local",
        "password": "okuyucu-parola-2", "role_id": read_only["id"],
        "is_active": True})
    token = app_client.post("/api/auth/token", data={
        "username": "esitleme-okur@test.local",
        "password": "okuyucu-parola-2"}).json()["access_token"]

    response = app_client.post("/api/admin/sync",
                               headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_sync_service_takes_the_queued_request(app_client, admin, sync_on,
                                               db, monkeypatch, database_url):
    """The service turns the queued row into its run instead of writing a
    second one beside it, so history shows one manual pass."""
    monkeypatch.setenv("DATABASE_URL", database_url)
    sys.path.insert(0, MIGRATION)
    try:
        sync = pytest.importorskip("sync")
    finally:
        sys.path.remove(MIGRATION)

    run_id = app_client.post("/api/admin/sync", headers=admin).json()["id"]
    claimed = sync.claim(db, "schedule")

    assert claimed is not None and claimed.id == run_id
    assert claimed.status == "running"
    assert claimed.trigger == "manual"
    assert claimed.window_from is not None
    assert sync.queued_request(db) is None
