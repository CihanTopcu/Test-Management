"""The charts over time: weekly pass rate, milestone progress, dashboard trend."""
from datetime import datetime, timedelta, timezone

PASSED, FAILED, BLOCKED = 1, 5, 2


def run_with(app_client, admin, project, suite, make_case, n, milestone_id=None):
    for i in range(n):
        make_case(f"Trend case {i}")
    body = {"suite_id": suite["id"], "name": "Trend koşumu", "include_all": True}
    if milestone_id:
        body["milestone_id"] = milestone_id
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json=body).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]
    return run, tests


def give(app_client, admin, test_id, status_id):
    response = app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                               json={"status_id": status_id})
    assert response.status_code == 201, response.text


def test_this_week_is_measured_and_empty_weeks_are_gaps(app_client, admin, project,
                                                        suite, make_case):
    _, tests = run_with(app_client, admin, project, suite, make_case, 4)
    give(app_client, admin, tests[0]["id"], PASSED)
    give(app_client, admin, tests[1]["id"], PASSED)
    give(app_client, admin, tests[2]["id"], FAILED)
    give(app_client, admin, tests[3]["id"], BLOCKED)

    weeks = app_client.get(f"/api/projects/{project['id']}/reports/pass-trend?weeks=8",
                           headers=admin).json()
    assert len(weeks) == 8
    today = datetime.now(timezone.utc).date()
    assert weeks[-1]["week"] == (today - timedelta(days=today.weekday())).isoformat()
    assert weeks[-1] == {**weeks[-1], "results": 4, "passed": 2, "failed": 1,
                         "other": 1, "pass_rate": 50.0}
    # nothing was entered before this week: gaps, not zeros
    assert all(w["pass_rate"] is None and w["results"] == 0 for w in weeks[:-1])


def test_milestone_progress_adds_up_its_sprints(app_client, admin, project, suite,
                                                make_case):
    release = app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                              json={"name": "Sürüm 1"}).json()
    sprint = app_client.post(f"/api/projects/{project['id']}/milestones", headers=admin,
                             json={"name": "Sprint 1", "parent_id": release["id"],
                                   "due_on": (datetime.now(timezone.utc)
                                              - timedelta(days=2)).isoformat()}).json()
    _, tests = run_with(app_client, admin, project, suite, make_case, 3,
                        milestone_id=sprint["id"])
    give(app_client, admin, tests[0]["id"], PASSED)
    give(app_client, admin, tests[1]["id"], FAILED)

    rows = {m["name"]: m for m in app_client.get(
        f"/api/projects/{project['id']}/reports/milestones", headers=admin).json()}
    for name in ("Sürüm 1", "Sprint 1"):
        assert (rows[name]["passed"], rows[name]["failed"], rows[name]["untested"]) == (1, 1, 1)
        assert rows[name]["total"] == 3 and rows[name]["pass_rate"] == 33
    assert rows["Sprint 1"]["overdue"] is True
    assert rows["Sürüm 1"]["overdue"] is False       # no date, never late
    # dated milestones first
    names = [m["name"] for m in app_client.get(
        f"/api/projects/{project['id']}/reports/milestones", headers=admin).json()]
    assert names.index("Sprint 1") < names.index("Sürüm 1")


def test_dashboard_carries_a_twelve_week_trend(app_client, admin, project, suite,
                                               make_case):
    _, tests = run_with(app_client, admin, project, suite, make_case, 2)
    give(app_client, admin, tests[0]["id"], PASSED)
    give(app_client, admin, tests[1]["id"], FAILED)

    data = app_client.get("/api/dashboard", headers=admin).json()
    assert len(data["trend_weeks"]) == 12
    row = next(p for p in data["projects"] if p["project_id"] == project["id"])
    assert len(row["trend"]) == 12
    assert row["trend"][-1] == 50.0 and row["trend"][0] is None
