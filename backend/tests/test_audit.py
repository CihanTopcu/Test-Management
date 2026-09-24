"""The audit log: who deleted what, and who changed the permissions."""


def entries(app_client, admin, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return app_client.get(f"/api/admin/audit?{query}", headers=admin).json()


def test_deleting_a_run_is_recorded(app_client, admin, project, suite,
                                    make_case):
    make_case("Denetlenecek")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Silinecek koşum",
                                "include_all": True}).json()
    app_client.delete(f"/api/runs/{run['id']}", headers=admin)

    log = entries(app_client, admin, entity_type="run", project_id=project["id"])
    assert log["total"] == 1
    line = log["items"][0]
    assert line["action"] == "delete"
    # the name is kept on the line, because the row it described is gone
    assert line["label"] == "Silinecek koşum"
    assert line["user_name"] == "Yönetici"
    assert line["detail"]["tests"] == 1


def test_role_change_keeps_before_and_after(app_client, admin):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    designer = next(r for r in roles if r["name"] == "Designer")
    before = designer["capabilities"]

    app_client.patch(f"/api/admin/roles/{designer['id']}", headers=admin,
                     json={"capabilities": ["read"]})

    log = entries(app_client, admin, entity_type="role")
    line = log["items"][0]
    assert line["detail"]["before"] == before
    assert line["detail"]["after"] == ["read"]

    app_client.patch(f"/api/admin/roles/{designer['id']}", headers=admin,
                     json={"capabilities": before})


def test_password_change_is_noted_but_not_stored(app_client, admin):
    created = app_client.post("/api/admin/users", headers=admin, json={
        "name": "Denetim kullanıcısı", "email": "denetim@test.local",
        "password": "ilk-parola-123", "is_active": True}).json()

    app_client.patch(f"/api/admin/users/{created['id']}", headers=admin,
                     json={"password": "gizli-yeni-parola"})

    log = entries(app_client, admin, entity_type="user")
    detail = log["items"][0]["detail"]
    assert detail["password"] == "changed"
    assert "gizli-yeni-parola" not in str(log)


def test_non_admins_cannot_read_the_log(app_client, admin):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    tester = next(r for r in roles if r["name"] == "Tester")
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Testçi", "email": "testci@test.local",
        "password": "testci-parola-1", "role_id": tester["id"],
        "is_active": True})

    token = app_client.post("/api/auth/token", data={
        "username": "testci@test.local",
        "password": "testci-parola-1"}).json()["access_token"]
    response = app_client.get("/api/admin/audit",
                              headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_a_rolled_back_action_leaves_no_line(app_client, admin, project, suite,
                                             make_case):
    """The entry shares the transaction with the change it describes."""
    make_case("Suite'i tutan case")
    before = entries(app_client, admin, entity_type="suite")["total"]

    refused = app_client.delete(f"/api/suites/{suite['id']}", headers=admin)
    assert refused.status_code == 400

    after = entries(app_client, admin, entity_type="suite")["total"]
    assert after == before
