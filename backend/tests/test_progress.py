"""Failed is one status, not "everything that is not passed".

Four screens used to compute failures by subtracting passed and untested from
the total, which swept every other status into the red segment. On the live
instance, which carries ten statuses, that was 6,114 tests reported as
failures that nobody had ever marked failed. A fresh install only has the
five TestRail ships with, so Blocked and Retest stand in for the rest here.
"""


def entered(app_client, admin, suite, make_case, statuses):
    """One run, one test per status asked for. Returns the run."""
    for i, _ in enumerate(statuses):
        make_case(f"Durum case {i}")
    run = app_client.post(
        f"/api/projects/{suite['project_id']}/runs", headers=admin,
        json={"suite_id": suite["id"], "name": "Durum koşumu",
              "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests",
                           headers=admin).json()["items"]
    for test, status in zip(tests, statuses):
        app_client.post(f"/api/tests/{test['id']}/results", headers=admin,
                        json={"status_id": status})
    return run


def test_run_list_counts_only_real_failures(app_client, admin, project, suite,
                                            make_case):
    # passed, failed, blocked, retest
    run = entered(app_client, admin, suite, make_case, [1, 5, 2, 4])

    row = next(r for r in app_client.get(
        f"/api/projects/{project['id']}/runs", headers=admin).json()
        if r["id"] == run["id"])

    assert row["passed_count"] == 1
    assert row["failed_count"] == 1, "blocked ve retest failed degildir"
    assert row["untested_count"] == 0
    other = (row["test_count"] - row["passed_count"]
             - row["failed_count"] - row["untested_count"])
    assert other == 2, "blocked + retest kendi kovasinda kalmali"


def test_dashboard_separates_other_from_failed(app_client, admin, project,
                                               suite, make_case):
    entered(app_client, admin, suite, make_case, [1, 5, 2, 4])

    row = next(p for p in app_client.get("/api/dashboard", headers=admin)
               .json()["projects"] if p["project_id"] == project["id"])

    assert row["failed"] == 1
    assert row["other"] == 2
    assert (row["passed"] + row["failed"] + row["other"] + row["untested"]
            == row["tests"]), "kovalar toplami test sayisini vermeli"


def test_today_run_row_separates_other_from_failed(app_client, admin, suite,
                                                   make_case):
    run = entered(app_client, admin, suite, make_case, [1, 5, 2, 4])

    row = next(r for r in app_client.get("/api/today?runs=50", headers=admin)
               .json()["my_runs"] if r["run_id"] == run["id"])

    assert row["passed"] == 1
    assert row["failed"] == 1
    assert row["other"] == 2
