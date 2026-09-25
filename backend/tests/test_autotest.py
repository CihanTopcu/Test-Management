"""Browser scenarios: the command language, the API, and a real run."""
import pathlib
import secrets

import pytest

from app.autotest.dsl import parse

PAGE = """<html><head><meta charset=utf-8><title>Deneme</title></head><body>
<form onsubmit="event.preventDefault();
  document.getElementById('msg').textContent='Hoş geldiniz '+document.getElementById('e').value">
<label for=e>E-posta</label><input id=e>
<input placeholder="Şifre" type=password>
<label><input type=checkbox> Beni hatırla</label>
<select aria-label="Ülke"><option>Almanya</option><option>Türkiye</option></select>
<button>Giriş Yap</button></form><p id=msg></p></body></html>"""


def test_commands_read_with_or_without_turkish_letters():
    steps, errors = parse('''# yorum
Git https://www.dgpays.com
TIKLA "Giriş Yap"
yaz “E-posta” = “a@b.com”
İşareti kaldır 'Beni hatırla'
Bekle 1,5''')
    assert not errors
    assert [(s.verb, s.args) for s in steps] == [
        ("git", ["https://www.dgpays.com"]), ("tikla", ["Giriş Yap"]),
        ("yaz", ["E-posta", "a@b.com"]), ("isaretikaldir", ["Beni hatırla"]),
        ("bekle", [1.5])]
    assert steps[1].line == 3


def test_mistakes_are_reported_by_line():
    _, errors = parse('Git https://x\nUç "a"\nYaz "yalnız alan"\nBekle 500')
    assert [(e.line, e.message.split(":")[0]) for e in errors] == [
        (2, "bilinmeyen komut"), (3, "beklenen biçim"), (4, "Bekle 0 ile 120 saniye arası olmalı")]


def test_scenario_rights_follow_cases_and_results(app_client, admin, project):
    base = f"/api/projects/{project['id']}/autotest/scenarios"
    s = app_client.post(base, headers=admin, json={
        "name": "Giriş", "steps": 'Git https://x\nGör "a"'}).json()
    assert app_client.get(base, headers=admin).json()[0]["name"] == "Giriş"

    # a Designer may edit scenarios but not run them
    roles = app_client.get("/api/admin/roles", headers=admin).json()["roles"]
    designer = next(r["id"] for r in roles if r["name"] == "Designer")
    email = f"tasarim-{secrets.token_hex(3)}@test.local"
    app_client.post("/api/admin/users", headers=admin, json={
        "name": "Tasarımcı", "email": email, "password": "tasarim-123-parola",
        "role_id": designer, "is_active": True})
    token = app_client.post("/api/auth/token", data={
        "username": email, "password": "tasarim-123-parola"}).json()["access_token"]
    them = {"Authorization": f"Bearer {token}"}
    assert app_client.patch(f"/api/autotest/scenarios/{s['id']}", headers=them,
                            json={"name": "Giriş (düzenlendi)"}).status_code == 200
    assert app_client.post(f"/api/autotest/scenarios/{s['id']}/runs",
                           headers=them).status_code == 403


def test_a_broken_scenario_is_not_started(app_client, admin, project, monkeypatch):
    from app.api.routers import autotest
    started = []
    monkeypatch.setattr(autotest, "launch", started.append)
    s = app_client.post(f"/api/projects/{project['id']}/autotest/scenarios", headers=admin,
                        json={"name": "Bozuk", "steps": 'Uç "a"'}).json()
    r = app_client.post(f"/api/autotest/scenarios/{s['id']}/runs", headers=admin)
    assert r.status_code == 422 and "1. satır" in r.json()["detail"]
    assert started == []


def test_drafting_without_a_key_says_so(app_client, admin, project):
    r = app_client.post("/api/autotest/draft", headers=admin, json={
        "project_id": project["id"], "text": "siteye gir ve giriş yap"})
    assert r.status_code == 503 and "ANTHROPIC_API_KEY" in r.json()["detail"]


@pytest.fixture
def browser(monkeypatch, tmp_path):
    """Runs start in-process and headless; returns the sample page's URL."""
    playwright = pytest.importorskip("playwright.sync_api")
    try:
        with playwright.sync_playwright() as p:
            p.chromium.launch().close()
    except Exception:                                   # noqa: BLE001
        pytest.skip("no Chromium for Playwright here")

    from app.api.routers import autotest
    from app.autotest import runner
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "autotest_headless", True)
    monkeypatch.setattr(settings, "autotest_slow_mo_ms", 0)
    monkeypatch.setattr(settings, "autotest_step_timeout_s", 2)
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path))
    # synchronous, one after another like the real batch process
    monkeypatch.setattr(autotest, "launch", lambda *ids: [runner.main(i) for i in ids])

    page = tmp_path / "giris.html"
    page.write_text(PAGE, encoding="utf-8")
    return pathlib.Path(page).as_uri()


def test_a_run_drives_a_real_browser(app_client, admin, project, browser):
    steps = f'''Git {browser}
Yaz "E-posta" = "ali@dgpays.com"
Yaz "Şifre" = "123"
İşaretle "Beni hatırla"
Seç "Ülke" = "Türkiye"
Tıkla "Giriş Yap"
Gör "Hoş geldiniz ali@dgpays.com"
Gör "Bu yazı yok"
Tıkla "Çıkış"'''
    s = app_client.post(f"/api/projects/{project['id']}/autotest/scenarios", headers=admin,
                        json={"name": "Gerçek koşum", "steps": steps}).json()
    run = app_client.post(f"/api/autotest/scenarios/{s['id']}/runs", headers=admin).json()
    run = app_client.get(f"/api/autotest/runs/{run['id']}", headers=admin).json()

    assert run["status"] == "failed"
    assert [x["status"] for x in run["log"]] == ["passed"] * 7 + ["failed", "skipped"]
    assert "Bu yazı yok" in run["log"][7]["message"]
    shot = app_client.get(f"/api/autotest/runs/{run['id']}/shots/7", headers=admin)
    assert shot.status_code == 200 and shot.content[:4] == b"\x89PNG"
    listed = app_client.get(f"/api/projects/{project['id']}/autotest/scenarios",
                            headers=admin).json()
    mine = next(x for x in listed if x["id"] == s["id"])
    assert mine["last_run"]["status"] == "failed" and mine["last_run"]["passed"] == 7


def test_secrets_are_encrypted_hidden_and_masked(app_client, admin, project, browser, db):
    from app.models import AutoVariable
    base = f"/api/projects/{project['id']}/autotest/variables"
    app_client.post(base, headers=admin, json={"name": "EPOSTA", "value": "ali@dgpays.com"})
    app_client.post(base, headers=admin, json={"name": "SIFRE", "value": "Gizli-123!",
                                                "is_secret": True})
    listed = {v["name"]: v for v in app_client.get(base, headers=admin).json()}
    assert listed["EPOSTA"]["value"] == "ali@dgpays.com"
    assert listed["SIFRE"]["value"] is None and listed["SIFRE"]["has_value"]
    stored = db.get(AutoVariable, listed["SIFRE"]["id"]).value
    assert "Gizli-123!" not in stored

    check = app_client.post("/api/autotest/check", headers=admin, json={
        "project_id": project["id"], "steps": 'Git https://x\nYaz "a" = "{{YOK}}"'}).json()
    assert check["errors"] == [{"line": 2, "message": "tanımsız değişken: {{YOK}}"}]

    steps = f'''Git {browser}
Yaz "E-posta" = "{{{{EPOSTA}}}}"
Yaz "Şifre" = "{{{{SIFRE}}}}"
Tıkla "Giriş Yap"
Gör "Hoş geldiniz ali@dgpays.com"
Gör "{{{{SIFRE}}}}"'''
    s = app_client.post(f"/api/projects/{project['id']}/autotest/scenarios", headers=admin,
                        json={"name": "Değişkenli", "steps": steps}).json()
    run = app_client.post(f"/api/autotest/scenarios/{s['id']}/runs", headers=admin).json()
    run = app_client.get(f"/api/autotest/runs/{run['id']}", headers=admin).json()
    assert [x["status"] for x in run["log"]] == ["passed"] * 5 + ["failed"]
    assert "{{SIFRE}}" in run["log"][2]["text"]               # the step as written
    assert "Gizli-123!" not in str(run)                        # never the value
    assert "••••" in run["log"][5]["message"]


def test_a_run_started_from_a_test_writes_its_result(app_client, admin, project, suite,
                                                      make_case, browser):
    case = make_case("Giriş otomasyonu")
    other = make_case("Başka case")
    base = f"/api/projects/{project['id']}/autotest/scenarios"
    assert app_client.post(base, headers=admin, json={
        "name": "x", "case_id": 999999999}).status_code == 400
    s = app_client.post(base, headers=admin, json={
        "name": "Giriş", "case_id": case["id"],
        "steps": f'Git {browser}\nTıkla "Giriş Yap"\nGör "Olmayan"'}).json()
    assert s["case_title"] == "Giriş otomasyonu"
    linked = app_client.get(f"/api/cases/{case['id']}/autotest", headers=admin).json()
    assert [x["name"] for x in linked] == ["Giriş"]
    assert app_client.get(f"/api/cases/{other['id']}/autotest", headers=admin).json() == []

    kosum = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Otomasyonlu koşum", "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{kosum['id']}/tests", headers=admin).json()["items"]
    test = next(t for t in tests if t["case_id"] == case["id"])

    run = app_client.post(f"/api/autotest/scenarios/{s['id']}/runs", headers=admin,
                          json={"test_id": test["id"]}).json()
    run = app_client.get(f"/api/autotest/runs/{run['id']}", headers=admin).json()
    assert run["status"] == "failed" and run["result_id"]

    results = app_client.get(f"/api/tests/{test['id']}/results", headers=admin).json()
    mine = next(r for r in results if r["id"] == run["result_id"])
    assert mine["status_id"] == 5
    assert f"#{run['id']}" in mine["comment"] and "Olmayan" in mine["comment"]
    assert [x["status_id"] for x in mine["step_results"]] == [1, 1, 5]
    assert len(mine["attachments"]) == 1
    fresh = app_client.get(f"/api/tests/{test['id']}", headers=admin).json()
    assert fresh["status_id"] == 5


def _run_with_cases(app_client, admin, project, suite, make_case, browser):
    """Three cases, two automated (one passes, one fails), in a new run."""
    good, bad, manual = (make_case("Otomatik geçen"), make_case("Otomatik kalan"),
                         make_case("Elle yapılan"))
    base = f"/api/projects/{project['id']}/autotest/scenarios"
    app_client.post(base, headers=admin, json={
        "name": "Geçen", "case_id": good["id"],
        "steps": f'Git {browser}' + chr(10) + 'Gör "Giriş Yap"'})
    app_client.post(base, headers=admin, json={
        "name": "Kalan", "case_id": bad["id"],
        "steps": f'Git {browser}' + chr(10) + 'Gör "Yok böyle bir şey"'})
    kosum = app_client.post(f"/api/projects/{project['id']}/runs", headers=admin, json={
        "suite_id": suite["id"], "name": "Toplu otomasyon", "include_all": True}).json()
    tests = app_client.get(f"/api/runs/{kosum['id']}/tests", headers=admin).json()["items"]
    by_case = {t["case_id"]: t for t in tests}
    return kosum, by_case[good["id"]], by_case[bad["id"]], by_case[manual["id"]]


def test_a_run_automates_its_linked_tests_in_one_go(app_client, admin, project, suite,
                                                     make_case, browser):
    kosum, good, bad, manual = _run_with_cases(app_client, admin, project, suite,
                                               make_case, browser)
    before = app_client.get(f"/api/runs/{kosum['id']}/autotest", headers=admin).json()
    assert before["total"] == 2
    assert {i["test_id"] for i in before["items"]} == {good["id"], bad["id"]}

    started = app_client.post(f"/api/runs/{kosum['id']}/autotest", headers=admin).json()
    assert started["started"] == 2

    after = app_client.get(f"/api/runs/{kosum['id']}/autotest", headers=admin).json()
    assert after["live"] == 0 and after["counts"]["passed"] == 1 and after["counts"]["failed"] == 1
    status = {t["id"]: t["status_id"] for t in app_client.get(
        f"/api/runs/{kosum['id']}/tests", headers=admin).json()["items"]}
    assert status[good["id"]] == 1 and status[bad["id"]] == 5
    assert status[manual["id"]] in (None, 3)                  # left alone


def test_a_waiting_batch_can_be_stopped(app_client, admin, project, suite, make_case,
                                        browser, monkeypatch):
    from app.api.routers import autotest
    queued = []
    monkeypatch.setattr(autotest, "launch", lambda *ids: queued.extend(ids))
    kosum, *_ = _run_with_cases(app_client, admin, project, suite, make_case, browser)
    app_client.post(f"/api/runs/{kosum['id']}/autotest", headers=admin)
    assert len(queued) == 2
    # a second press while they wait does not queue them twice
    assert app_client.post(f"/api/runs/{kosum['id']}/autotest",
                           headers=admin).json()["started"] == 0

    assert app_client.post(f"/api/runs/{kosum['id']}/autotest/stop",
                           headers=admin).json()["stopped"] == 2
    state = app_client.get(f"/api/runs/{kosum['id']}/autotest", headers=admin).json()
    assert state["live"] == 0 and state["counts"]["stopped"] == 2


DYNAMIC_PAGE = """<html><head><meta charset=utf-8><title>Dinamik</title></head><body>
<label for=e>E-posta</label><input id=e>
<button onclick="n=(window.n||0)+1;window.n=n;document.getElementById('c').textContent='Sayaç '+n">Artır</button>
<span id=c>Sayaç 0</span>
<p class=item>bir</p><p class=item>iki</p>
<p id=ord>SIP-12345</p></body></html>"""


def test_blocks_are_read_as_a_tree():
    steps, errors = parse("""Tekrarla 2
  Eğer "a"
    Tıkla "b"
  Değilse
    Ata X = "1"
  Bitti
Bitti
Kaydet "css:#x" -> SONUC
Say "css:.s" = 3""")
    assert not errors
    loop = steps[0]
    assert loop.verb == "tekrarla" and loop.args == [2]
    branch = loop.children[0]
    assert [s.verb for s in branch.children] == ["tikla"]
    assert [s.verb for s in branch.otherwise] == ["ata"]
    assert steps[1].args == ["css:#x", "SONUC"] and steps[2].args == ["css:.s", 3]

    _, errors = parse('Eğer "a"\nTıkla "b"\nBitti\nBitti\nDeğilse\nTekrarla 2')
    assert [e.message for e in errors] == [
        "Bitti'ye karşılık gelen bir blok yok",
        "Değilse yalnız bir Eğer bloğunun içinde olur",
        "Tekrarla bloğu Bitti ile kapanmamış"]


def test_dynamic_scenario_with_a_data_set(app_client, admin, project, browser, tmp_path):
    page = tmp_path / "dinamik.html"
    page.write_text(DYNAMIC_PAGE, encoding="utf-8")
    base = f"/api/projects/{project['id']}/autotest/scenarios"
    app_client.post(base, headers=admin, json={
        "name": "Sayfayı aç", "steps": f"Git {pathlib.Path(page).as_uri()}"})
    steps = """Kullan "Sayfayı aç"
Yaz "E-posta" = "{{EPOSTA}}"
Değer "E-posta" = "{{BEKLENEN}}"
Kaydet "css:#ord" -> SIPARIS
Ata KOPYA = "{{SIPARIS}}/{{satir}}"
Yaz "E-posta" = "{{KOPYA}}"
Tekrarla 3
  Tıkla "Artır"
Bitti
Gör "Sayaç 3"
Say "css:.item" = 2
Eğer "Kampanya"
  Tıkla "Olmayan düğme"
Değilse
  Gör "SIP-12345"
Bitti
Yaz "E-posta" = "{{rastgele.tckn}}"
"""
    data = "EPOSTA;BEKLENEN\nali@dgpays.com;ali@dgpays.com\nveli@dgpays.com;yanlis@dgpays.com"
    check = app_client.post("/api/autotest/check", headers=admin, json={
        "project_id": project["id"], "steps": steps, "data": data}).json()
    assert check["errors"] == [] and check["rows"] == 2

    s = app_client.post(base, headers=admin, json={
        "name": "Dinamik", "steps": steps, "data": data}).json()
    run = app_client.post(f"/api/autotest/scenarios/{s['id']}/runs", headers=admin).json()
    run = app_client.get(f"/api/autotest/runs/{run['id']}", headers=admin).json()
    log = run["log"]

    rows = [x for x in log if x.get("kind") == "row"]
    assert [x["status"] for x in rows] == ["passed", "failed"]
    assert run["status"] == "failed"
    first = [x for x in log if x.get("row") == 1 and x.get("kind") != "row"]
    assert all(x["status"] == "passed" for x in first)
    notes = {x["text"]: x.get("note") for x in first}
    assert notes['Kaydet "css:#ord" -> SIPARIS'] == "SIPARIS = SIP-12345"
    assert notes['Ata KOPYA = "{{SIPARIS}}/{{satir}}"'] == "KOPYA = SIP-12345/1"
    assert sum(1 for x in first if x["text"] == 'Tıkla "Artır"') == 3
    assert next(x for x in first if x["text"] == 'Gör "SIP-12345"')["depth"] == 1
    assert not any(x["text"] == 'Tıkla "Olmayan düğme"' for x in first)
    # the included scenario's step is logged one level in
    assert first[1]["text"].startswith("Git file:") and first[1]["depth"] == 1

    second = [x for x in log if x.get("row") == 2 and x.get("kind") != "row"]
    failed = next(x for x in second if x["status"] == "failed")
    assert failed["text"] == 'Değer "E-posta" = "{{BEKLENEN}}"'
    assert "yanlis@dgpays.com" in failed["message"]
    assert second[-1]["status"] == "skipped"
