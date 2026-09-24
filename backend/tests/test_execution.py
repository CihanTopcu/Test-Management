"""Runs, results and the arithmetic the status roll-ups depend on."""
import pytest


@pytest.fixture
def run(app_client, admin, project, suite, make_case):
    for i in range(3):
        make_case(f"Koşum case {i}")
    response = app_client.post(f"/api/projects/{project['id']}/runs",
                               headers=admin, json={
                                   "suite_id": suite["id"], "name": "Koşum",
                                   "include_all": True})
    assert response.status_code == 201, response.text
    return response.json()


def test_run_starts_untested(app_client, admin, run):
    tests = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]
    assert len(tests) == 3
    assert {t["status_id"] for t in tests} == {3}

    summary = app_client.get(f"/api/runs/{run['id']}/summary", headers=admin).json()
    assert summary["total"] == 3


def test_result_moves_the_test_and_the_summary(app_client, admin, run):
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    response = app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                               json={"status_id": 1, "comment": "geçti"})
    assert response.status_code == 201, response.text

    detail = app_client.get(f"/api/tests/{test_id}", headers=admin).json()
    assert detail["status_id"] == 1
    summary = app_client.get(f"/api/runs/{run['id']}/summary", headers=admin).json()
    assert summary["by_status"].get("1") == 1


def test_step_results_round_trip(app_client, admin, run, app_client_unused=None):
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin, json={
        "status_id": 5,
        "step_results": [
            {"idx": 0, "content": "a", "expected": "x", "actual": "x", "status_id": 1},
            {"idx": 1, "content": "b", "expected": "y", "actual": "z", "status_id": 5},
        ],
    })
    results = app_client.get(f"/api/tests/{test_id}/results", headers=admin).json()
    steps = results[0]["step_results"]
    assert [(s["idx"], s["status_id"], s["actual"]) for s in steps] == [
        (0, 1, "x"), (1, 5, "z")]


def test_deleting_a_result_rolls_the_status_back(app_client, admin, run):
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 1})
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 5})
    assert app_client.get(f"/api/tests/{test_id}",
                          headers=admin).json()["status_id"] == 5

    newest = app_client.get(f"/api/tests/{test_id}/results",
                            headers=admin).json()[0]
    assert app_client.delete(f"/api/results/{newest['id']}",
                             headers=admin).status_code == 204
    assert app_client.get(f"/api/tests/{test_id}",
                          headers=admin).json()["status_id"] == 1


def test_last_result_removed_returns_to_untested(app_client, admin, run):
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 1})
    only = app_client.get(f"/api/tests/{test_id}/results", headers=admin).json()[0]
    app_client.delete(f"/api/results/{only['id']}", headers=admin)
    assert app_client.get(f"/api/tests/{test_id}",
                          headers=admin).json()["status_id"] == 3


def test_adding_and_removing_cases(app_client, admin, project, suite, run,
                                   make_case):
    extra = make_case("Sonradan yazılan case")
    response = app_client.post(f"/api/runs/{run['id']}/tests", headers=admin,
                               json={"case_ids": [extra["id"]]})
    assert response.json() == {"added": 1, "skipped": 0}

    tests = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]
    assert len(tests) == 4

    response = app_client.request(
        "DELETE", f"/api/runs/{run['id']}/tests", headers=admin,
        json={"case_ids": [tests[0]["id"], tests[1]["id"]]})
    assert response.json() == {"removed": 2}
    assert app_client.get(f"/api/runs/{run['id']}/tests",
                          headers=admin).json()["total"] == 2


def test_adding_a_case_twice_is_a_no_op(app_client, admin, run, make_case):
    extra = make_case("Bir kez eklenecek")
    app_client.post(f"/api/runs/{run['id']}/tests", headers=admin,
                    json={"case_ids": [extra["id"]]})
    again = app_client.post(f"/api/runs/{run['id']}/tests", headers=admin,
                            json={"case_ids": [extra["id"]]})
    assert again.json() == {"added": 0, "skipped": 1}


def test_deleting_a_run_takes_its_results(app_client, admin, project, run):
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                    json={"status_id": 1})

    assert app_client.delete(f"/api/runs/{run['id']}",
                             headers=admin).status_code == 204
    assert app_client.get(f"/api/runs/{run['id']}", headers=admin).status_code == 404
    assert app_client.get(f"/api/tests/{test_id}", headers=admin).status_code == 404


def test_test_detail_carries_the_case_steps(app_client, admin, project, suite,
                                            make_case):
    make_case("Adımlı", steps=[{"content": "Tek adım", "expected": "Sonuç"}])
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Adım koşumu",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]

    detail = app_client.get(f"/api/tests/{test_id}", headers=admin).json()
    assert [s["content"] for s in detail["steps"]] == ["Tek adım"]
    assert detail["steps"][0]["status_id"] is None

    app_client.post(f"/api/tests/{test_id}/results", headers=admin, json={
        "status_id": 5,
        "step_results": [{"idx": 0, "content": "Tek adım", "expected": "Sonuç",
                          "actual": "olmadı", "status_id": 5}]})
    detail = app_client.get(f"/api/tests/{test_id}", headers=admin).json()
    assert detail["steps"][0]["status_id"] == 5


def test_the_grid_pages_and_reports_the_true_total(app_client, admin, project,
                                                   suite, make_case):
    """The run grid used to show one page and give no sign there was more.

    287 runs in the migrated data hold over 500 tests; the largest holds
    10,062. The endpoint now says how many matched, not how many it returned.
    """
    for i in range(12):
        make_case(f"Sayfalama case {i:02d}")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Sayfalı koşum",
                                "include_all": True}).json()

    first = app_client.get(f"/api/runs/{run['id']}/tests?limit=5",
                           headers=admin).json()
    assert first["total"] == 12
    assert len(first["items"]) == 5

    second = app_client.get(f"/api/runs/{run['id']}/tests?limit=5&offset=5",
                            headers=admin).json()
    assert second["total"] == 12
    assert {t["id"] for t in first["items"]} & {t["id"] for t in second["items"]} == set()


def test_filters_reach_rows_outside_the_page(app_client, admin, project, suite,
                                             make_case):
    for i in range(6):
        make_case(f"Filtre case {i}")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Filtreli koşum",
                                "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests",
                           headers=admin).json()["items"]
    # mark the last one, which a first page of five would not contain
    app_client.post(f"/api/tests/{tests[-1]['id']}/results", headers=admin,
                    json={"status_id": 1})

    passed = app_client.get(f"/api/runs/{run['id']}/tests?status_id=1&limit=5",
                            headers=admin).json()
    assert passed["total"] == 1
    assert passed["items"][0]["id"] == tests[-1]["id"]

    found = app_client.get(f"/api/runs/{run['id']}/tests?q=case 5",
                           headers=admin).json()
    assert found["total"] == 1
