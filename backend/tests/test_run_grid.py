"""The run grid: tests in section order, and handing tests out in bulk."""
import secrets

from sqlalchemy import select

from app.models import Notification


def section(app_client, admin, suite, name, parent=None):
    body = {"suite_id": suite["id"], "name": name}
    if parent:
        body["parent_id"] = parent
    response = app_client.post("/api/sections", headers=admin, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def case(app_client, admin, section_id, title):
    response = app_client.post("/api/cases", headers=admin,
                               json={"section_id": section_id, "title": title})
    assert response.status_code == 201, response.text
    return response.json()


def test_tests_come_in_section_tree_order(app_client, admin, project, suite):
    """By test id a run read as its cases' creation order. It follows the
    suite's tree now, children after their parent, and says which section
    each test is in."""
    first = section(app_client, admin, suite, "Giriş")
    second = section(app_client, admin, suite, "Ödeme")
    nested = section(app_client, admin, suite, "Giriş › Hatalı parola", parent=first["id"])

    # written out of order on purpose
    case(app_client, admin, second["id"], "Ödeme alınır")
    case(app_client, admin, nested["id"], "Yanlış parola reddedilir")
    case(app_client, admin, first["id"], "Doğru parola ile girilir")

    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Sıralı koşum", "include_all": True}).json()
    items = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]

    assert [t["title"] for t in items] == [
        "Doğru parola ile girilir", "Yanlış parola reddedilir", "Ödeme alınır"]
    assert [t["section_id"] for t in items] == [first["id"], nested["id"], second["id"]]


def test_bulk_assign_hands_tests_out_with_one_notice(app_client, admin, project,
                                                     suite, section, make_case, db):
    for n in range(3):
        make_case(f"Atanacak {n}")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Atama koşumu", "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{run['id']}/tests", headers=admin).json()["items"]

    email = f"atanan-{secrets.token_hex(3)}@test.local"
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Atanan kişi", "email": email, "password": "atanan-parola-1",
        "is_active": True})
    uid = next(u["id"] for u in app_client.get("/api/users", headers=admin).json()
               if u["email"] == email)

    response = app_client.post(f"/api/runs/{run['id']}/bulk-assign", headers=admin,
                               json={"test_ids": [t["id"] for t in tests],
                                     "assignedto_id": uid})
    assert response.json()["updated"] == 3
    after = app_client.get(f"/api/runs/{run['id']}/tests?assignedto_id={uid}",
                           headers=admin).json()
    assert after["total"] == 3

    notices = db.scalars(select(Notification).where(
        Notification.user_id == uid, Notification.kind == "test_assigned")).all()
    assert len(notices) == 1 and "3 test" in notices[0].subject

    # assigning the same again changes nothing and says so
    again = app_client.post(f"/api/runs/{run['id']}/bulk-assign", headers=admin,
                            json={"test_ids": [t["id"] for t in tests],
                                  "assignedto_id": uid})
    assert again.json()["updated"] == 0

    cleared = app_client.post(f"/api/runs/{run['id']}/bulk-assign", headers=admin,
                              json={"test_ids": [tests[0]["id"]], "assignedto_id": None})
    assert cleared.json()["updated"] == 1


def test_bulk_assign_needs_result_rights(app_client, admin, project, suite, make_case):
    make_case("Yetki denemesi")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Yetki koşumu", "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]

    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    read_only = next(r for r in roles if r["name"] == "Read-only")
    email = f"okur-{secrets.token_hex(3)}@test.local"
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Okuyucu", "email": email, "password": "okuyucu-parola-1",
        "role_id": read_only["id"], "is_active": True})
    token = app_client.post("/api/auth/token", data={
        "username": email, "password": "okuyucu-parola-1"}).json()["access_token"]

    response = app_client.post(f"/api/runs/{run['id']}/bulk-assign",
                               headers={"Authorization": f"Bearer {token}"},
                               json={"test_ids": [test_id], "assignedto_id": None})
    assert response.status_code == 403
