"""Attachment upload, retrieval and the rule protecting migrated files."""
import io

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def upload(app_client, admin, **data):
    return app_client.post(
        "/api/attachments", headers=admin,
        files={"file": ("ekran.png", io.BytesIO(PNG), "image/png")},
        data=data)


def test_upload_and_fetch(app_client, admin, make_case):
    case = make_case("Ekli case")
    response = upload(app_client, admin, entity_type="case",
                      entity_id=case["id"])
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["id"].startswith("u")

    listing = app_client.get(
        f"/api/attachments?entity_type=case&entity_id={case['id']}",
        headers=admin).json()
    assert [a["id"] for a in listing] == [uploaded["id"]]

    blob = app_client.get(f"/api/attachments/{uploaded['id']}", headers=admin)
    assert blob.status_code == 200
    assert blob.content == PNG


def test_same_bytes_twice_reuse_one_row(app_client, admin, make_case):
    """The content hash is the filename, so a re-upload is not a new file."""
    case = make_case("Aynı dosya")
    first = upload(app_client, admin, entity_type="case",
                   entity_id=case["id"]).json()
    second = upload(app_client, admin, entity_type="case",
                    entity_id=case["id"]).json()
    assert first["id"] == second["id"]


def test_delete_removes_it(app_client, admin, make_case):
    case = make_case("Silinecek ek")
    uploaded = upload(app_client, admin, entity_type="case",
                      entity_id=case["id"]).json()
    assert app_client.delete(f"/api/attachments/{uploaded['id']}",
                             headers=admin).status_code == 204
    listing = app_client.get(
        f"/api/attachments?entity_type=case&entity_id={case['id']}",
        headers=admin).json()
    assert listing == []


def test_result_attachment_is_bound_on_save(app_client, admin, project, suite,
                                            make_case):
    make_case("Ekli sonuç")
    run = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin,
                          json={"suite_id": suite["id"], "name": "Ek koşumu",
                                "include_all": True}).json()
    test_id = app_client.get(f"/api/runs/{run['id']}/tests",
                             headers=admin).json()["items"][0]["id"]

    # uploaded first, bound afterwards: a failed save must not leave a file
    # pointing at a result that does not exist
    uploaded = upload(app_client, admin, entity_type="result").json()
    app_client.post(f"/api/tests/{test_id}/results", headers=admin, json={
        "status_id": 5, "comment": "hata",
        "attachment_ids": [uploaded["id"]]})

    results = app_client.get(f"/api/tests/{test_id}/results", headers=admin).json()
    assert [a["filename"] for a in results[0]["attachments"]] == ["ekran.png"]
