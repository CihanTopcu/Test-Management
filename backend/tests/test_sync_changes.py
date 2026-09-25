"""What a sync pass brought in, read back from its window."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import update


def test_a_pass_lists_the_testrail_results_in_its_window(app_client, admin, project,
                                                         suite, make_case, db):
    from app.models import Result, SyncRun

    make_case("Senkron case A")
    make_case("Senkron case B")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "TestRail'den gelen koşum", "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]
    comment = "**_____ Faz İzleme Adımları _____**\n **1** - Kart ekranı açılır"
    ids = []
    for test, status in zip(tests, (1, 5)):
        ids.append(app_client.post(f"/api/tests/{test['id']}/results", headers=admin,
                                   json={"status_id": status, "comment": comment,
                                         "defects": "PM-42"}).json()["id"])
    # one more, entered here: it must not show up as brought in by the sync
    native = app_client.post(f"/api/tests/{tests[0]['id']}/results", headers=admin,
                             json={"status_id": 1}).json()["id"]

    # the first two stand in for rows the loader wrote from TestRail
    db.execute(update(Result).where(Result.id.in_(ids))
               .values(testrail_id=Result.id))
    now = datetime.now(timezone.utc)
    sync = SyncRun(started_on=now, finished_on=now + timedelta(seconds=5), status="ok",
                   trigger="schedule", window_from=now - timedelta(hours=1), counts={})
    db.add(sync)
    db.commit()

    data = app_client.get(f"/api/admin/sync/{sync.id}/changes", headers=admin).json()
    listed = {r["id"] for r in data["results"]}
    assert set(ids) <= listed and native not in listed
    mine = [r for r in data["results"] if r["id"] in ids]
    assert {r["status"] for r in mine} == {"Passed", "Failed"}
    assert all(r["comment"] == "1 - Kart ekranı açılır" for r in mine)   # banner skipped
    assert all(r["defects"] == "PM-42" and r["run_name"] == "TestRail'den gelen koşum" for r in mine)

    tester = next(t for t in data["testers"] if t["name"] == "Yönetici")
    assert tester["passed"] >= 1 and tester["failed"] >= 1
    assert any(r["id"] == run["id"] for r in data["runs"])


def test_a_pass_still_running_says_so(app_client, admin, db):
    from app.models import SyncRun
    sync = SyncRun(started_on=datetime.now(timezone.utc), status="running",
                   trigger="manual", counts={})
    db.add(sync)
    db.commit()
    data = app_client.get(f"/api/admin/sync/{sync.id}/changes", headers=admin).json()
    assert data["window"] is None and data["note"]
    db.delete(sync)
    db.commit()
