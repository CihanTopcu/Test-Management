"""The landing page.

Built against how this team actually works rather than how a test tool
assumes people work: nobody here assigns tests and runs are opened by
automation, so the sections that a generic tool would lead with come back
empty. These check that the page still carries its weight when they do.
"""
from datetime import datetime, timedelta, timezone


def test_today_is_never_empty(app_client, admin, project, suite, make_case):
    """A front door that is blank on a quiet morning is a bad front door."""
    make_case("Bir case")

    data = app_client.get("/api/today", headers=admin).json()
    names = [p["name"] for p in data["projects"]]
    assert project["name"] in names, "proje seridi her zaman dolu olmali"
    entry = next(p for p in data["projects"] if p["name"] == project["name"])
    assert entry["cases"] == 1


def test_recent_runs_have_no_date_floor(app_client, admin, project, suite,
                                        make_case, db):
    """A cut-over instance can sit quiet for weeks.

    An earlier version windowed this to seven days, which emptied the
    section on exactly the mornings somebody would go looking.
    """
    from sqlalchemy import text

    make_case("Eski kosum case'i")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Eski koşum",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 1})

    db.execute(text("UPDATE results SET created_on = now() - interval '90 days'"
                    " WHERE test_id = :t"), {"t": test_id})
    db.commit()

    # asked wide on purpose: the endpoint returns the most recent runs, and
    # every other test in the session has been creating fresher ones
    data = app_client.get("/api/today?runs=50", headers=admin).json()
    mine = [r for r in data["my_runs"] if r["run_id"] == run["id"]]
    assert mine, "90 gunluk kosum da listelenmeli"
    assert mine[0]["last_result_on"] is not None, "yasi satirda yazmali"


def test_failures_are_limited_to_the_last_day(app_client, admin, project,
                                              suite, make_case, db):
    from sqlalchemy import text

    make_case("Kirilan")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Kırılma koşumu",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 5})

    fresh = app_client.get("/api/today", headers=admin).json()
    assert any(f["test_id"] == test_id for f in fresh["failures"])

    db.execute(text("UPDATE results SET created_on = now() - interval '3 days'"
                    " WHERE test_id = :t"), {"t": test_id})
    db.commit()

    stale = app_client.get("/api/today", headers=admin).json()
    assert not any(f["test_id"] == test_id for f in stale["failures"])


def test_ancient_milestones_do_not_count_as_upcoming(app_client, admin,
                                                     project):
    """One of these was 1,463 days overdue. Four years late is a cleanup
    task, not today's work."""
    now = datetime.now(timezone.utc)
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Terk edilmiş",
                          "due_on": (now - timedelta(days=400)).isoformat()})
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Yeni geçti",
                          "due_on": (now - timedelta(days=3)).isoformat()})
    app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                    json={"name": "Bu hafta",
                          "due_on": (now + timedelta(days=4)).isoformat()})

    data = app_client.get("/api/today", headers=admin).json()
    names = [m["name"] for m in data["milestones"]]
    assert "Bu hafta" in names
    assert "Yeni geçti" in names
    assert "Terk edilmiş" not in names


def test_the_page_says_when_assignment_is_unused(app_client, admin, project,
                                                 suite, make_case):
    """An empty section that explains itself beats one that just sits there."""
    data = app_client.get("/api/today", headers=admin).json()
    assert "assignment_in_use" in data
    assert isinstance(data["assignment_in_use"], bool)
