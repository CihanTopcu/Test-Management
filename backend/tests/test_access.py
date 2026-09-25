"""Who may open which project.

Before these, reading was never checked: a "No Access" account could list
every project, open any case and find it through search. The rules are
TestRail's, in its order -- administrator, own membership, groups, the
project's default access, global role.
"""
import secrets

import pytest

from app.models import Group, GroupMember


def role_id(app_client, admin, name):
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    return next(r["id"] for r in roles if r["name"] == name)


@pytest.fixture
def person(app_client, admin):
    """A fresh account with the given global role; returns (headers, id)."""
    def _make(global_role="Tester"):
        email = f"kisi-{secrets.token_hex(3)}@test.local"
        app_client.post("/api/admin/users", headers=admin, json={
            "name": email.split("@")[0], "email": email,
            "password": "kisi-parola-123",
            "role_id": role_id(app_client, admin, global_role),
            "is_active": True})
        users = app_client.get("/api/users", headers=admin).json()
        uid = next(u["id"] for u in users if u["email"] == email)
        token = app_client.post("/api/auth/token", data={
            "username": email, "password": "kisi-parola-123"}).json()["access_token"]
        return {"Authorization": f"Bearer {token}"}, uid
    return _make


def visible(app_client, headers):
    return {p["id"] for p in app_client.get("/api/projects", headers=headers).json()}


def test_no_access_account_sees_nothing(app_client, admin, person, project, make_case):
    case = make_case("Gizli senaryo")
    headers, _ = person("No Access")

    assert project["id"] not in visible(app_client, headers)
    assert app_client.get(f"/api/projects/{project['id']}", headers=headers).status_code == 404
    assert app_client.get(f"/api/cases/{case['id']}", headers=headers).status_code == 404
    hits = app_client.get("/api/search?q=Gizli", headers=headers).json()
    assert case["id"] not in {c["id"] for c in hits["cases"]}


def test_default_access_no_access_closes_a_project(app_client, admin, person,
                                                   project, suite):
    headers, uid = person("Tester")
    assert project["id"] in visible(app_client, headers)   # global role: open

    app_client.patch(f"/api/projects/{project['id']}", headers=admin,
                     json={"default_role_id": role_id(app_client, admin, "No Access")})
    assert project["id"] not in visible(app_client, headers)
    assert app_client.get(f"/api/projects/{project['id']}/suites",
                          headers=headers).status_code == 404
    assert app_client.get(f"/api/suites/{suite['id']}/cases",
                          headers=headers).status_code == 404

    # a membership of their own opens it again, for them alone
    app_client.put(f"/api/projects/{project['id']}/members", headers=admin,
                   json={"user_id": uid, "role_id": role_id(app_client, admin, "Tester")})
    assert project["id"] in visible(app_client, headers)

    other, _ = person("Tester")
    assert project["id"] not in visible(app_client, other)


def test_a_group_grant_opens_a_closed_project(app_client, admin, person,
                                              project, db):
    headers, uid = person("Tester")
    app_client.patch(f"/api/projects/{project['id']}", headers=admin,
                     json={"default_role_id": role_id(app_client, admin, "No Access")})
    assert project["id"] not in visible(app_client, headers)

    group = Group(name=f"Grup {secrets.token_hex(2)}")
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=uid))
    db.commit()

    response = app_client.put(f"/api/projects/{project['id']}/groups", headers=admin,
                              json={"group_id": group.id,
                                    "role_id": role_id(app_client, admin, "Read-only")})
    assert response.status_code == 200, response.text
    assert project["id"] in visible(app_client, headers)
    # read-only through the group: reading yes, writing no
    assert app_client.post(f"/api/projects/{project['id']}/suites", headers=headers,
                           json={"name": "Olmaz"}).status_code == 403


def test_own_membership_beats_the_group(app_client, admin, person, project, db):
    headers, uid = person("Tester")
    group = Group(name=f"Grup {secrets.token_hex(2)}")
    db.add(group)
    db.flush()
    db.add(GroupMember(group_id=group.id, user_id=uid))
    db.commit()
    app_client.put(f"/api/projects/{project['id']}/groups", headers=admin,
                   json={"group_id": group.id,
                         "role_id": role_id(app_client, admin, "Lead")})
    app_client.put(f"/api/projects/{project['id']}/members", headers=admin,
                   json={"user_id": uid,
                         "role_id": role_id(app_client, admin, "No Access")})

    assert project["id"] not in visible(app_client, headers)


def test_a_lead_cannot_hand_out_more_than_they_hold(app_client, admin, person,
                                                    project):
    lead_headers, lead_id = person("Tester")
    app_client.put(f"/api/projects/{project['id']}/members", headers=admin,
                   json={"user_id": lead_id, "role_id": role_id(app_client, admin, "Lead")})
    _, someone = person("Tester")

    # a Designer is within what a Lead holds
    ok = app_client.put(f"/api/projects/{project['id']}/members", headers=lead_headers,
                        json={"user_id": someone,
                              "role_id": role_id(app_client, admin, "Designer")})
    assert ok.status_code == 200, ok.text

    # Admin is not -- for somebody else or for themselves
    for target in (someone, lead_id):
        response = app_client.put(f"/api/projects/{project['id']}/members",
                                  headers=lead_headers,
                                  json={"user_id": target,
                                        "role_id": role_id(app_client, admin, "Admin")})
        assert response.status_code == 403


def test_dashboard_counts_only_what_you_can_see(app_client, admin, person,
                                                project, make_case):
    make_case("Sayılacak mı")
    headers, _ = person("Tester")
    before = app_client.get("/api/dashboard", headers=headers).json()
    assert project["id"] in {p["project_id"] for p in before["projects"]}

    app_client.patch(f"/api/projects/{project['id']}", headers=admin,
                     json={"default_role_id": role_id(app_client, admin, "No Access")})
    after = app_client.get("/api/dashboard", headers=headers).json()
    assert project["id"] not in {p["project_id"] for p in after["projects"]}
    assert after["totals"]["projects"] == before["totals"]["projects"] - 1
    assert after["totals"]["cases"] < before["totals"]["cases"]


def test_reports_are_closed_with_their_project(app_client, admin, person, project):
    headers, _ = person("Tester")
    url = f"/api/projects/{project['id']}/reports/coverage"
    assert app_client.get(url, headers=headers).status_code == 200
    app_client.patch(f"/api/projects/{project['id']}", headers=admin,
                     json={"default_role_id": role_id(app_client, admin, "No Access")})
    assert app_client.get(url, headers=headers).status_code == 404


def test_admin_sees_a_closed_project(app_client, admin, project):
    app_client.patch(f"/api/projects/{project['id']}", headers=admin,
                     json={"default_role_id": role_id(app_client, admin, "No Access")})
    assert project["id"] in visible(app_client, admin)
