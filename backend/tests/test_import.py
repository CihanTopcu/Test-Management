"""Spreadsheet import: column guessing, step splitting, dry runs."""
import io


def upload(app_client, admin, suite, body: bytes, name="cases.csv", **data):
    return app_client.post(
        f"/api/suites/{suite['id']}/import", headers=admin,
        files={"file": (name, io.BytesIO(body), "text/csv")},
        data={"dry_run": "true", **data})


SEMI = (
    "Başlık;Bölüm;Öncelik;Adımlar;Beklenen\n"
    "Giriş denemesi;Login;High;Parolayı gir;Ana sayfa açılır\n"
    "Çıkış denemesi;Login;Low;Çıkışa bas;Giriş ekranı gelir\n"
).encode("utf-8-sig")


def test_headers_are_guessed(app_client, admin, suite):
    report = upload(app_client, admin, suite, SEMI).json()
    assert report["mapping"] == {
        "Başlık": "title", "Bölüm": "section", "Öncelik": "priority",
        "Adımlar": "steps", "Beklenen": "expected"}
    assert report["total_rows"] == 2
    assert report["would_create"] == 2
    assert report["new_sections"] == ["Login"]


def test_dry_run_writes_nothing(app_client, admin, suite):
    before = app_client.get(f"/api/suites/{suite['id']}/cases",
                            headers=admin).json()["total"]
    upload(app_client, admin, suite, SEMI)
    after = app_client.get(f"/api/suites/{suite['id']}/cases",
                           headers=admin).json()["total"]
    assert after == before


def test_commit_creates_cases_and_sections(app_client, admin, suite):
    report = upload(app_client, admin, suite, SEMI, dry_run="false").json()
    assert report["created"] == 2

    listing = app_client.get(f"/api/suites/{suite['id']}/cases",
                             headers=admin).json()
    titles = {c["title"] for c in listing["items"]}
    assert {"Giriş denemesi", "Çıkış denemesi"} <= titles

    tree = app_client.get(f"/api/suites/{suite['id']}/sections",
                          headers=admin).json()
    assert "Login" in [n["name"] for n in tree]


def test_comma_separated_file_also_works(app_client, admin, suite):
    body = ("title,section,priority\n"
            "Virgüllü case,Bölüm A,Medium\n").encode("utf-8")
    report = upload(app_client, admin, suite, body).json()
    assert report["mapping"]["title"] == "title"
    assert report["would_create"] == 1


def test_multiline_cell_becomes_several_steps(app_client, admin, suite):
    body = ('Başlık;Adımlar;Beklenen\n'
            '"Çok adımlı";"Birinci\nİkinci";"Bir sonuç\nİki sonuç"\n'
            ).encode("utf-8-sig")
    report = upload(app_client, admin, suite, body, dry_run="false").json()
    assert report["created"] == 1

    listing = app_client.get(f"/api/suites/{suite['id']}/cases",
                             headers=admin).json()
    case_id = next(c["id"] for c in listing["items"] if c["title"] == "Çok adımlı")
    case = app_client.get(f"/api/cases/{case_id}", headers=admin).json()
    assert [(s["content"], s["expected"]) for s in case["steps"]] == [
        ("Birinci", "Bir sonuç"), ("İkinci", "İki sonuç")]


def test_custom_field_column_is_matched_by_label(app_client, admin, suite):
    """Headers are matched against the labels an admin gave the fields."""
    created = app_client.post("/api/admin/fields", headers=admin, json={
        "entity": "case", "system_name": "custom_sprint", "label": "Sprint",
        "field_type": "string", "is_global": True})
    assert created.status_code in (201, 400), created.text

    body = "Başlık;Sprint\nAlanlı case;S-42\n".encode("utf-8-sig")
    report = upload(app_client, admin, suite, body, dry_run="false").json()
    assert report["mapping"].get("Sprint") == "custom_sprint"

    listing = app_client.get(f"/api/suites/{suite['id']}/cases",
                             headers=admin).json()
    case_id = next(c["id"] for c in listing["items"] if c["title"] == "Alanlı case")
    case = app_client.get(f"/api/cases/{case_id}", headers=admin).json()
    assert case["custom"]["custom_sprint"] == "S-42"


def test_rows_without_a_title_are_reported(app_client, admin, suite):
    body = "Başlık;Bölüm\n;Login\nDolu;Login\n".encode("utf-8-sig")
    report = upload(app_client, admin, suite, body).json()
    assert report["would_create"] == 1
    assert any("baslik bos" in s for s in report["skipped"])


def test_a_file_without_a_title_column_is_refused(app_client, admin, suite):
    body = "Bölüm;Öncelik\nLogin;High\n".encode("utf-8-sig")
    response = upload(app_client, admin, suite, body)
    assert response.status_code == 400


def test_empty_file_is_refused(app_client, admin, suite):
    assert upload(app_client, admin, suite, b"").status_code == 400
