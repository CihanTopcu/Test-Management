"""Draft scenario commands from a free-text description.

Used once, when a scenario is written: the tester reads and edits what comes
back, saves it, and every run after that is the plain commands -- the same
each time, and free. Nothing here runs a browser.
"""
import httpx

from ..config import get_settings
from .dsl import help_lines, parse
from .variables import BUILTINS

API = "https://api.anthropic.com/v1/messages"


class AIError(Exception):
    pass


def enabled() -> bool:
    return bool(get_settings().anthropic_api_key)


def _system() -> str:
    commands = "\n".join(f"- {line}" for line in help_lines())
    builtins = ", ".join("{{" + b + "}}" for b in sorted(BUILTINS))
    return f"""Bir web test senaryosunu, aşağıdaki komut dilinde adımlara çeviriyorsun.
Her satıra tek komut yaz. Yalnızca komutları yaz: açıklama, numara, kod bloğu yok.

Komutlar:
{commands}

Hazır değerler (her kullanımda yeni değer üretir): {builtins}
Bir değeri birden çok adımda kullanmak için önce Ata ile saklayın.

Kurallar:
- Hedefler çift tırnak içinde ve kullanıcının ekranda gördüğü yazıdır: düğme yazısı,
  alan etiketi ya da alanın içindeki ipucu yazısı. Tahmin etmen gerekiyorsa en olası
  görünen yazıyı kullan.
- Bir işlemden sonra sonucu doğrulamak için Gör, Görme ya da Adres ekle.
- Metinde adres yoksa ve ilk adımın hangi sayfada başladığı belli değilse
  ilk satıra "# Başlangıç adresini yazın" yorumunu ve ardından Git https:// koy.
- Emin olmadığın bir adımın üstüne # ile başlayan kısa bir not yaz.
- Şifre gibi gizli değerler metinde verilmemişse "****" yaz."""


def draft(text: str, start_url: str | None = None) -> dict:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise AIError("yapay zekâ ayarlı değil (ANTHROPIC_API_KEY)")
    prompt = text.strip()
    if start_url:
        prompt = f"Başlangıç adresi: {start_url}\n\n{prompt}"
    try:
        r = httpx.post(API, timeout=60, headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }, json={
            "model": settings.autotest_ai_model,
            "max_tokens": 2000,
            "system": _system(),
            "messages": [{"role": "user", "content": prompt}],
        })
    except httpx.HTTPError as e:
        raise AIError(f"yapay zekâya ulaşılamadı: {e}") from None
    if r.status_code != 200:
        raise AIError(f"yapay zekâ {r.status_code} döndü: {r.text[:200]}")
    body = r.json()
    steps = "".join(b.get("text", "") for b in body.get("content", [])
                    if b.get("type") == "text").strip()
    # a model that wraps the answer in a code fence anyway
    steps = "\n".join(l for l in steps.splitlines() if not l.strip().startswith("```"))
    _, errors = parse(steps)
    return {"steps": steps,
            "errors": [{"line": e.line, "message": e.message} for e in errors]}
