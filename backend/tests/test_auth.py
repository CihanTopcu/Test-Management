"""Authentication, API tokens and the permission checks."""


def test_login_and_me(app_client, admin):
    response = app_client.get("/api/auth/me", headers=admin)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.local"


def test_wrong_password_is_rejected(app_client):
    response = app_client.post("/api/auth/token", data={
        "username": "admin@test.local", "password": "yanlış"})
    assert response.status_code == 401


def test_anonymous_access_is_refused(app_client):
    # a clean jar: the shared client still holds the session cookie that the
    # login handed out, and <img> tags rely on that cookie working
    app_client.cookies.clear()
    assert app_client.get("/api/projects").status_code == 401


def test_api_token_works_everywhere(app_client, admin):
    """A token used to reach only the automation routes.

    Everything else went through a separate dependency that understood the
    JWT alone, so a script that could post results could not read the project
    list it needed to find the run.
    """
    created = app_client.post("/api/tokens", headers=admin,
                              json={"name": "otomasyon"})
    assert created.status_code == 201, created.text
    secret = created.json()["token"]
    assert secret.startswith("tm_")

    headers = {"Authorization": f"Bearer {secret}"}
    assert app_client.get("/api/projects", headers=headers).status_code == 200
    assert app_client.get("/api/catalog", headers=headers).status_code == 200
    assert app_client.get("/api/auth/me", headers=headers).status_code == 200


def test_revoked_token_stops_working(app_client, admin):
    created = app_client.post("/api/tokens", headers=admin,
                              json={"name": "iptal edilecek"}).json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    assert app_client.get("/api/projects", headers=headers).status_code == 200

    app_client.delete(f"/api/tokens/{created['id']}", headers=admin)
    assert app_client.get("/api/projects", headers=headers).status_code == 401


def test_read_only_user_cannot_write(app_client, admin, project):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    read_only = next(r for r in roles if r["name"] == "Read-only")

    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Okuyucu", "email": "okuyucu@test.local",
        "password": "okuyucu-parola-1", "role_id": read_only["id"],
        "is_active": True})

    token = app_client.post("/api/auth/token", data={
        "username": "okuyucu@test.local",
        "password": "okuyucu-parola-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert app_client.get("/api/projects", headers=headers).status_code == 200
    response = app_client.post(f"/api/projects/{project['id']}/suites",
                               headers=headers, json={"name": "Olmaz"})
    assert response.status_code == 403


def test_project_role_overrides_the_global_one(app_client, admin, project):
    """Leading one product and only reading another is the whole point."""
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    read_only = next(r for r in roles if r["name"] == "Read-only")
    lead = next(r for r in roles if r["name"] == "Lead")

    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Takım lideri", "email": "lider@test.local",
        "password": "lider-parola-1", "role_id": read_only["id"],
        "is_active": True})
    users = app_client.get("/api/users", headers=admin).json()
    lider = next(u for u in users if u["email"] == "lider@test.local")

    app_client.put(f"/api/projects/{project['id']}/members", headers=admin,
                   json={"user_id": lider["id"], "role_id": lead["id"]})

    token = app_client.post("/api/auth/token", data={
        "username": "lider@test.local",
        "password": "lider-parola-1"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = app_client.post(f"/api/projects/{project['id']}/suites",
                               headers=headers, json={"name": "Lider suite"})
    assert response.status_code == 201, response.text
