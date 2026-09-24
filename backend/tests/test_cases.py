"""Cases: custom fields, steps, history, soft delete."""


def test_create_case_with_steps(app_client, admin, make_case):
    case = make_case("Adımlı case", steps=[
        {"content": "Birinci adım", "expected": "Birinci sonuç"},
        {"content": "İkinci adım", "expected": "İkinci sonuç"},
    ])
    assert [s["content"] for s in case["steps"]] == ["Birinci adım", "İkinci adım"]
    assert [s["idx"] for s in case["steps"]] == [0, 1]


def test_rewriting_steps_does_not_collide(app_client, admin, make_case):
    """Steps are unique on (case_id, idx).

    Clearing the collection alone lets SQLAlchemy order the new rows ahead of
    the removals, and the second save fails on the unique constraint. This is
    the regression test for that.
    """
    case = make_case("Adımları değişen case", steps=[
        {"content": "a", "expected": "1"}, {"content": "b", "expected": "2"}])

    for attempt in range(3):
        response = app_client.patch(f"/api/cases/{case['id']}", headers=admin, json={
            "steps": [{"content": f"yeni {attempt}", "expected": "x"}]})
        assert response.status_code == 200, response.text
        assert len(response.json()["steps"]) == 1


def test_custom_fields_merge_rather_than_replace(app_client, admin, make_case):
    """A patch touching one field must not wipe the others."""
    case = make_case("Özel alanlı case", custom={
        "custom_preconds": "Önkoşul metni", "custom_sprint": "S-1"})

    response = app_client.patch(f"/api/cases/{case['id']}", headers=admin,
                                json={"custom": {"custom_sprint": "S-2"}})
    assert response.status_code == 200, response.text
    custom = response.json()["custom"]
    assert custom["custom_sprint"] == "S-2"
    assert custom["custom_preconds"] == "Önkoşul metni"


def test_custom_field_cleared_with_null(app_client, admin, make_case):
    case = make_case("Temizlenecek alan", custom={"custom_sprint": "S-1"})
    response = app_client.patch(f"/api/cases/{case['id']}", headers=admin,
                                json={"custom": {"custom_sprint": None}})
    assert "custom_sprint" not in response.json()["custom"]


def test_history_records_every_change(app_client, admin, make_case):
    case = make_case("Geçmişi olan case")
    app_client.patch(f"/api/cases/{case['id']}", headers=admin,
                     json={"title": "Yeni başlık"})
    app_client.patch(f"/api/cases/{case['id']}", headers=admin,
                     json={"refs": "JIRA-1"})

    history = app_client.get(f"/api/cases/{case['id']}/history",
                             headers=admin).json()
    fields = {c["field"] for entry in history for c in entry["changes"]}
    assert {"title", "refs"} <= fields
    # newest first, the way the page renders it
    assert history[0]["created_on"] >= history[-1]["created_on"]


def test_soft_delete_keeps_the_row(app_client, admin, make_case, suite):
    case = make_case("Silinecek case")
    assert app_client.delete(f"/api/cases/{case['id']}",
                             headers=admin).status_code == 204

    # gone from the listing
    listing = app_client.get(f"/api/suites/{suite['id']}/cases?limit=50",
                             headers=admin).json()
    assert case["id"] not in [c["id"] for c in listing["items"]]
    # but still readable, because runs point at it
    detail = app_client.get(f"/api/cases/{case['id']}", headers=admin).json()
    assert detail["is_deleted"] is True
