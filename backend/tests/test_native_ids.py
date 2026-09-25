"""Rows created here never share an id with TestRail's.

The cut-over sync writes by id. With sequences standing just past the
highest imported id, the next case or result created here took the id
TestRail would hand out next, and the sync overwrote it. Everything created
in this application now comes from NATIVE_ID_BASE up.
"""
# imported inside the tests: at module level it would build the app's
# engine before conftest has pointed it at the test database
NATIVE_ID_BASE = 1_000_000_000


def test_created_rows_take_native_ids(app_client, admin, project, suite, make_case):
    from app.bootstrap import NATIVE_ID_BASE as base
    assert base == NATIVE_ID_BASE
    case = make_case("Yerel kimlik")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Yerel koşum", "include_all": True}).json()
    test = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"][0]
    result = app_client.post(f"/api/tests/{test['id']}/results", headers=admin,
                             json={"status_id": 1}).json()

    for kind, value in (("project", project["id"]), ("suite", suite["id"]),
                        ("case", case["id"]), ("run", run["id"]),
                        ("test", test["id"]), ("result", result["id"])):
        assert value >= NATIVE_ID_BASE, f"{kind} id {value} is in TestRail's range"


def test_the_range_survives_being_asked_again(app_client, admin, project, make_case):
    from app.bootstrap import ensure_native_id_range
    before = make_case("Önce")["id"]
    ensure_native_id_range()           # startup and every sync call it
    after = make_case("Sonra")["id"]
    assert after > before >= NATIVE_ID_BASE
