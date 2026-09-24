"""Case-library health reports.

Each of these exists because auditing the migrated data turned up a number
nobody had seen: 7,722 cases that both pass and fail, 4,146 duplicates of a
case in the same folder, and a third of the library never executed.
"""
from datetime import datetime, timedelta, timezone


def url(project, path, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"/api/projects/{project['id']}/reports/{path}?{query}"


def _run_with(app_client, admin, project, suite, name="Koşum"):
    response = app_client.post(f"/api/projects/{project['id']}/runs",
                               headers=admin, json={
                                   "suite_id": suite["id"], "name": name,
                                   "include_all": True})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_test_that_only_passes_is_not_flaky(app_client, admin, project,
                                              suite, make_case):
    make_case("Hep geçen")
    run = _run_with(app_client, admin, project, suite)
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    for _ in range(6):
        app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                        json={"status_id": 1})

    report = app_client.get(url(project, "flaky"), headers=admin).json()
    assert report["items"] == []


def test_a_test_that_flaps_is_reported(app_client, admin, project, suite,
                                       make_case):
    case = make_case("Bir geçen bir kalan")
    run = _run_with(app_client, admin, project, suite)
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    for status in (1, 5, 1, 5, 1, 5):
        app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                        json={"status_id": status})

    report = app_client.get(url(project, "flaky"), headers=admin).json()
    assert len(report["items"]) == 1
    item = report["items"][0]
    assert item["case_id"] == case["id"]
    assert item["passed"] == 3 and item["failed"] == 3
    # three of each: it changed its mind every single time
    assert item["flip_rate"] == 50


def test_the_threshold_is_respected(app_client, admin, project, suite,
                                    make_case):
    """Two failures out of ten is a bug, not a flake."""
    make_case("Iki kez kalan")
    run = _run_with(app_client, admin, project, suite)
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    for status in (1, 1, 1, 1, 1, 5, 5):
        app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                        json={"status_id": status})

    assert app_client.get(url(project, "flaky"),
                          headers=admin).json()["items"] == []
    # asked for a lower bar, it shows up
    loosened = app_client.get(url(project, "flaky", min_each=2),
                              headers=admin).json()
    assert len(loosened["items"]) == 1


def test_the_window_excludes_old_flapping(app_client, admin, project, suite,
                                          make_case, db):
    """A case that flapped in 2022 and has been steady since is not news."""
    from sqlalchemy import text

    make_case("Eskiden kararsızdı")
    run = _run_with(app_client, admin, project, suite)
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]
    for status in (1, 5, 1, 5, 1, 5):
        app_client.post(f"/api/tests/{test_id}/results", headers=admin,
                        json={"status_id": status})

    assert len(app_client.get(url(project, "flaky", days=90),
                              headers=admin).json()["items"]) == 1

    # push them back beyond the window; the API always stamps now()
    old = datetime.now(timezone.utc) - timedelta(days=400)
    db.execute(text("UPDATE results SET created_on = :when WHERE test_id = :t"),
               {"when": old, "t": test_id})
    db.commit()

    assert app_client.get(url(project, "flaky", days=90),
                          headers=admin).json()["items"] == []
    # still there if you ask for a window that reaches them
    assert len(app_client.get(url(project, "flaky", days=500),
                              headers=admin).json()["items"]) == 1


def test_duplicate_titles_in_one_section(app_client, admin, project, suite,
                                         section, make_case):
    make_case("Aynı isim")
    make_case("Aynı isim")
    make_case("  aynı İSİM  ")     # trimmed and folded: still the same
    make_case("Farklı isim")

    report = app_client.get(url(project, "duplicates"), headers=admin).json()
    assert len(report["items"]) == 1
    group = report["items"][0]
    assert group["count"] == 3
    assert group["section_id"] == section["id"]
    assert group["section_name"] == section["name"]
    assert len(group["case_ids"]) == 3


def test_the_same_title_in_two_sections_is_not_a_duplicate(app_client, admin,
                                                           project, suite,
                                                           section, make_case):
    """Two folders legitimately test the same thing in different contexts."""
    other = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Başka bölüm"}).json()
    make_case("Ortak başlık")
    app_client.post("/api/cases", headers=admin, json={
        "section_id": other["id"], "title": "Ortak başlık"})

    report = app_client.get(url(project, "duplicates"), headers=admin).json()
    assert report["items"] == []


def test_never_run_lists_only_unexecuted_cases(app_client, admin, project,
                                               suite, make_case):
    make_case("Koşulacak")
    unused = make_case("Hiç koşulmayacak")
    run = _run_with(app_client, admin, project, suite)

    # drop the second one from the run, so it has never been executed
    tests = app_client.get(f"/api/runs/{run['id']}/tests",
                           headers=admin).json()["items"]
    drop = next(t for t in tests if t["case_id"] == unused["id"])
    app_client.request("DELETE", f"/api/runs/{run['id']}/tests", headers=admin,
                       json={"case_ids": [drop["id"]]})

    report = app_client.get(url(project, "never-run"), headers=admin).json()
    assert report["total"] == 1
    assert report["items"][0]["case_id"] == unused["id"]
    assert report["items"][0]["section_name"] == "Bölüm"


def test_a_deleted_case_is_not_reported_as_unrun(app_client, admin, project,
                                                 suite, make_case):
    case = make_case("Silinmiş ve koşulmamış")
    app_client.delete(f"/api/cases/{case['id']}", headers=admin)

    report = app_client.get(url(project, "never-run"), headers=admin).json()
    assert report["total"] == 0


def _automation_field(app_client, admin):
    """The team's own IsAutomated field, created the way an admin would."""
    created = app_client.post("/api/admin/fields", headers=admin, json={
        "entity": "case", "system_name": "custom_automation_type",
        "label": "IsAutomated", "field_type": "dropdown", "is_global": True,
        "options": [{"value": 2, "label": "Automated"},
                    {"value": 8, "label": "Non-Automated"},
                    {"value": 11, "label": "Ready to Automation"}],
    })
    assert created.status_code in (201, 400), created.text


def test_automation_backlog_ranks_by_how_often_it_is_run(
        app_client, admin, project, suite, make_case):
    _automation_field(app_client, admin)
    rare = make_case("Nadiren koşulan", custom={"custom_automation_type": 11})
    often = make_case("Sık koşulan", custom={"custom_automation_type": 11})
    make_case("Zaten otomatik", custom={"custom_automation_type": 2})

    # three runs for everything, then two more that hold only the busy case
    _run_with(app_client, admin, project, suite, "Tam koşum")
    for i in range(2):
        response = app_client.post(f"/api/projects/{project['id']}/runs",
                                   headers=admin, json={
                                       "suite_id": suite["id"],
                                       "name": f"Dar koşum {i}",
                                       "include_all": False,
                                       "case_ids": [often["id"]]})
        assert response.status_code == 201, response.text

    report = app_client.get(url(project, "automation-backlog"),
                            headers=admin).json()
    assert report["configured"] is True
    assert report["field_label"] == "IsAutomated"

    titles = [i["title"] for i in report["items"]]
    assert titles[0] == "Sık koşulan", "en cok kosulan basta olmali"
    assert "Zaten otomatik" not in titles, "otomatize olanlar listede olmamali"
    assert report["items"][0]["runs"] == 3
    assert report["items"][0]["status"] == "Ready to Automation"

    # the rarely-run one is still there, just lower
    assert rare["id"] in [i["case_id"] for i in report["items"]]


def test_the_status_spread_marks_which_values_mean_manual(
        app_client, admin, project, suite, make_case):
    _automation_field(app_client, admin)
    make_case("Otomatik", custom={"custom_automation_type": 2})
    make_case("Elle", custom={"custom_automation_type": 8})

    report = app_client.get(url(project, "automation-backlog"),
                            headers=admin).json()
    spread = {s["label"]: s for s in report["by_status"]}
    assert spread["Automated"]["is_manual"] is False
    assert spread["Non-Automated"]["is_manual"] is True


def test_a_project_with_nothing_manual_says_so(app_client, admin, project,
                                               suite, make_case):
    """An empty table with no explanation reads like a broken report."""
    _automation_field(app_client, admin)
    make_case("Hepsi otomatik", custom={"custom_automation_type": 2})

    report = app_client.get(url(project, "automation-backlog"),
                            headers=admin).json()
    assert report["items"] == []
    assert "elle koşulan olarak işaretli case yok" in report["detail"]


def test_manual_cases_that_never_ran_are_explained_not_hidden(
        app_client, admin, project, suite, make_case):
    """The ranking is by run count, so an unrun case cannot be in the table.
    Saying nothing would look like the report had failed."""
    _automation_field(app_client, admin)
    make_case("Elle ama hic kosulmamis", custom={"custom_automation_type": 8})

    report = app_client.get(url(project, "automation-backlog"),
                            headers=admin).json()
    assert report["items"] == []
    assert "hiçbiri bir koşuma girmemiş" in report["detail"]
