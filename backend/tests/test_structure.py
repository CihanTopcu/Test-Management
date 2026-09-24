"""Sections, suites and the rules around deleting them."""


def test_section_tree_nests_and_counts(app_client, admin, suite, section,
                                       make_case):
    child = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Alt", "parent_id": section["id"]}).json()
    assert child["depth"] == 1

    make_case("Üstteki case")
    app_client.post("/api/cases", headers=admin,
                    json={"section_id": child["id"], "title": "Alttaki case"})

    tree = app_client.get(f"/api/suites/{suite['id']}/sections",
                          headers=admin).json()
    assert len(tree) == 1
    assert tree[0]["case_count"] == 1
    assert tree[0]["children"][0]["case_count"] == 1


def test_moving_a_section_restamps_the_subtree(app_client, admin, suite,
                                               section):
    child = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Alt", "parent_id": section["id"]}).json()
    grandchild = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Torun", "parent_id": child["id"]}).json()
    other = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Diğer kök"}).json()

    response = app_client.patch(f"/api/sections/{child['id']}", headers=admin,
                                json={"parent_id": other["id"]})
    assert response.json()["depth"] == 1

    tree = app_client.get(f"/api/suites/{suite['id']}/sections",
                          headers=admin).json()
    moved = next(n for n in tree if n["id"] == other["id"])
    assert moved["children"][0]["children"][0]["id"] == grandchild["id"]
    assert moved["children"][0]["children"][0]["depth"] == 2


def test_a_section_cannot_move_into_its_own_subtree(app_client, admin, suite,
                                                    section):
    child = app_client.post("/api/sections", headers=admin, json={
        "suite_id": suite["id"], "name": "Alt", "parent_id": section["id"]}).json()

    response = app_client.patch(f"/api/sections/{section['id']}", headers=admin,
                                json={"parent_id": child["id"]})
    assert response.status_code == 400

    response = app_client.patch(f"/api/sections/{section['id']}", headers=admin,
                                json={"parent_id": section["id"]})
    assert response.status_code == 400


def test_deleting_a_section_soft_deletes_its_cases(app_client, admin, suite,
                                                   section, make_case):
    case = make_case("Bölümle birlikte gidecek")
    assert app_client.delete(f"/api/sections/{section['id']}",
                             headers=admin).status_code == 204

    # the section is hidden, not dropped: the case still needs somewhere to hang
    tree = app_client.get(f"/api/suites/{suite['id']}/sections",
                          headers=admin).json()
    assert section["id"] not in [n["id"] for n in tree]

    detail = app_client.get(f"/api/cases/{case['id']}", headers=admin).json()
    assert detail["is_deleted"] is True


def test_empty_section_is_removed_outright(app_client, admin, suite, section):
    assert app_client.delete(f"/api/sections/{section['id']}",
                             headers=admin).status_code == 204
    tree = app_client.get(f"/api/suites/{suite['id']}/sections",
                          headers=admin).json()
    assert tree == []


def test_suite_with_cases_refuses_to_go(app_client, admin, suite, make_case):
    make_case("Suite'i tutan case")
    response = app_client.delete(f"/api/suites/{suite['id']}", headers=admin)
    assert response.status_code == 400
    assert "case" in response.json()["detail"]


def test_empty_suite_can_be_deleted(app_client, admin, project):
    suite = app_client.post(f"/api/projects/{project['id']}/suites",
                            headers=admin, json={"name": "Boş"}).json()
    assert app_client.delete(f"/api/suites/{suite['id']}",
                             headers=admin).status_code == 204


def test_renaming(app_client, admin, suite, section):
    assert app_client.patch(f"/api/suites/{suite['id']}", headers=admin,
                            json={"name": "Yeni suite"}).json()["name"] == "Yeni suite"
    assert app_client.patch(f"/api/sections/{section['id']}", headers=admin,
                            json={"name": "Yeni bölüm"}).json()["name"] == "Yeni bölüm"
