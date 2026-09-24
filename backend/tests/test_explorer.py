"""The project-wide case library.

The reports page could say that a third of the library has never been run and
offered no way to see which third: cases live under suites, so the only case
list was suite-scoped. These check the filters a chart links into, because a
drill-down that quietly returns the wrong set is worse than no drill-down.
"""


def test_filters_cases_across_the_whole_project(app_client, admin, project,
                                                suite, make_case):
    make_case("Kosulacak case")
    make_case("Kosulmayacak case")

    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Koşum",
                                "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests",
                           headers=admin).json()["items"]
    keep = next(t for t in tests if t["title"] == "Kosulacak case")
    app_client.post(f"/api/tests/{keep['id']}/results", headers=admin,
                    json={"status_id": 1})

    # every test in a run counts as executed, result or not -- being in a run
    # is what "has been run" means here, and the coverage report agrees
    page = app_client.get(f"/api/projects/{project['id']}/cases?executed=yes",
                          headers=admin).json()
    assert page["total"] == 2
    assert all(c["runs"] == 1 for c in page["items"])

    never = app_client.get(f"/api/projects/{project['id']}/cases?executed=no",
                           headers=admin).json()
    assert never["total"] == 0


def test_never_run_is_the_complement_of_executed(app_client, admin, project,
                                                 suite, make_case):
    make_case("Hiç koşulmayan")

    page = app_client.get(f"/api/projects/{project['id']}/cases?executed=no",
                          headers=admin).json()
    titles = [c["title"] for c in page["items"]]
    assert "Hiç koşulmayan" in titles
    assert all(c["runs"] == 0 for c in page["items"])

    coverage = app_client.get(
        f"/api/projects/{project['id']}/reports/coverage", headers=admin).json()
    assert page["total"] == coverage["cases"] - coverage["executed"], (
        "gezgin ve kapsam raporu ayni sayiyi vermeli")


def test_refs_filter_splits_the_library(app_client, admin, project, suite,
                                        make_case):
    linked = make_case("Gereksinimli")
    make_case("Gereksinimsiz")
    app_client.patch(f"/api/cases/{linked['id']}", headers=admin,
                     json={"refs": "JIRA-1"})

    with_refs = app_client.get(
        f"/api/projects/{project['id']}/cases?refs=with", headers=admin).json()
    without = app_client.get(
        f"/api/projects/{project['id']}/cases?refs=without", headers=admin).json()

    assert [c["title"] for c in with_refs["items"]] == ["Gereksinimli"]
    assert "Gereksinimsiz" in [c["title"] for c in without["items"]]
    # an empty string is not a reference, whatever the column says
    assert all(c["refs"] for c in with_refs["items"])


def test_distribution_buckets_carry_the_id_they_count(app_client, admin,
                                                      project, suite, make_case):
    """A bar that cannot say which type it counted cannot become a link."""
    case = make_case("Tipli case")
    app_client.patch(f"/api/cases/{case['id']}", headers=admin,
                     json={"type_id": 2})

    dist = app_client.get(
        f"/api/projects/{project['id']}/reports/property-distribution?by=type",
        headers=admin).json()
    bucket = next(b for b in dist["buckets"] if b["id"] == 2)

    filtered = app_client.get(
        f"/api/projects/{project['id']}/cases?type_id=2", headers=admin).json()
    assert filtered["total"] == bucket["count"], (
        "cubugun sayisi ile acilan listenin sayisi ayni olmali")


def test_suite_buckets_link_to_their_own_suite(app_client, admin, project,
                                               suite, make_case):
    make_case("Suite case'i")

    coverage = app_client.get(
        f"/api/projects/{project['id']}/reports/coverage", headers=admin).json()
    bucket = next(b for b in coverage["by_suite"] if b["id"] == suite["id"])

    filtered = app_client.get(
        f"/api/projects/{project['id']}/cases?suite_id={suite['id']}",
        headers=admin).json()
    assert filtered["total"] == bucket["count"]
    assert all(c["suite_id"] == suite["id"] for c in filtered["items"])


def test_run_count_is_scoped_to_the_project(app_client, admin, project, suite,
                                            make_case):
    """A case's run count must not pick up runs from other projects.

    The first version aggregated all 1,064,011 test rows to answer a question
    about one project, which was both slow and wrong at the edges.
    """
    make_case("Sayilacak case")
    for i in range(2):
        app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                        json={"suite_id": suite["id"], "name": f"Koşum {i}",
                              "include_all": True})

    page = app_client.get(
        f"/api/projects/{project['id']}/cases?sort=runs", headers=admin).json()
    row = next(c for c in page["items"] if c["title"] == "Sayilacak case")
    assert row["runs"] == 2
