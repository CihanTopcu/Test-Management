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


def test_a_run_drives_a_real_browser(app_client, admin, project, monkeypatch, tmp_path):
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
    monkeypatch.setattr(autotest, "launch", runner.main)     # in-process, synchronous

    page = tmp_path / "giris.html"
    page.write_text(PAGE, encoding="utf-8")
    steps = f'''Git {pathlib.Path(page).as_uri()}
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
