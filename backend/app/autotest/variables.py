"""{{NAME}} placeholders in scenario steps, and the values behind them.

A secret is encrypted with a key derived from SECRET_KEY: a copy of the
database alone does not give away the test passwords in it. Rotating
SECRET_KEY makes the stored secrets unreadable; they then have to be
entered again, which the page says when it happens.
"""
import base64
import csv
import hashlib
import random
import re
import string
import uuid
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings

NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_.]*)\s*\}\}")
MASK = "••••"


def _fernet() -> Fernet:
    digest = hashlib.sha256(("autotest:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def seal(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def unseal(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def referenced(source: str) -> set[str]:
    return {m.group(1) for m in PLACEHOLDER.finditer(source)}


def load(session: Session, project_id: int) -> tuple[dict[str, str], set[str], set[str]]:
    """Values by name, the secret values (for masking), and the names whose
    secret could not be decrypted."""
    from ..models import AutoVariable
    values, secrets, broken = {}, set(), set()
    for v in session.scalars(select(AutoVariable).where(AutoVariable.project_id == project_id)):
        if v.is_secret:
            plain = unseal(v.value)
            if plain is None:
                broken.add(v.name)
                continue
            values[v.name] = plain
            if plain:
                secrets.add(plain)
        else:
            values[v.name] = v.value
    return values, secrets, broken


def _tckn() -> str:
    """A number that passes the Turkish ID checksum, as forms validate it."""
    d = [random.randint(1, 9)] + [random.randint(0, 9) for _ in range(8)]
    d.append(((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10)
    d.append(sum(d) % 10)
    return "".join(map(str, d))


FIRST = ["Ali", "Ayşe", "Mehmet", "Zeynep", "Can", "Elif", "Emre", "Deniz", "Ece", "Burak"]
LAST = ["Yılmaz", "Kaya", "Demir", "Şahin", "Çelik", "Yıldız", "Aydın", "Öztürk", "Arslan"]

# {{name}} values made up at the moment they are used. Each use is a fresh
# value; Ata keeps one for later steps: Ata EPOSTA = "{{rastgele.eposta}}"
BUILTINS = {
    "rastgele.sayi": lambda: str(random.randint(100000, 999999)),
    "rastgele.metin": lambda: "".join(random.choices(string.ascii_lowercase, k=8)),
    "rastgele.eposta": lambda: f"test.{uuid.uuid4().hex[:10]}@dgtest.local",
    "rastgele.telefon": lambda: "5" + str(random.randint(30, 59)) + str(random.randint(1000000, 9999999)),
    "rastgele.tckn": _tckn,
    "rastgele.ad": lambda: random.choice(FIRST),
    "rastgele.soyad": lambda: random.choice(LAST),
    "uuid": lambda: str(uuid.uuid4()),
    "bugun": lambda: datetime.now().strftime("%d.%m.%Y"),
    "yarin": lambda: (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y"),
    "simdi": lambda: datetime.now().strftime("%d.%m.%Y %H:%M"),
    "zaman": lambda: str(int(datetime.now().timestamp())),
}


def is_known(name: str) -> bool:
    return name in BUILTINS


def fill(text: str, values: dict[str, str]) -> str:
    def one(m):
        name = m.group(1)
        if name in values:
            return str(values[name])
        if name in BUILTINS:
            return BUILTINS[name]()
        return m.group(0)
    return PLACEHOLDER.sub(one, text)


def unresolved(text: str) -> list[str]:
    return [m.group(1) for m in PLACEHOLDER.finditer(text)]


def parse_data(text: str | None) -> tuple[list[dict[str, str]], str | None]:
    """A scenario's data set: a header line and one row per run of the
    scenario. Tab, semicolon or comma separated -- what a spreadsheet gives
    when cells are copied."""
    if not text or not text.strip():
        return [], None
    lines = [l for l in text.strip().splitlines() if l.strip()]
    sep = "\t" if "\t" in lines[0] else ";" if ";" in lines[0] else ","
    rows = list(csv.reader(lines, delimiter=sep))
    header = [h.strip() for h in rows[0]]
    bad = [h for h in header if not NAME.match(h)]
    if bad:
        return [], f"veri seti başlığında geçersiz ad: {', '.join(bad)} (harf, rakam, _)"
    if len(rows) < 2:
        return [], "veri setinde başlıktan sonra en az bir satır olmalı"
    if len(rows) > 201:
        return [], "veri seti en çok 200 satır olabilir"
    out = []
    for n, row in enumerate(rows[1:], 2):
        if len(row) != len(header):
            return [], f"veri setinin {n}. satırında {len(row)} değer var, başlıkta {len(header)}"
        out.append({h: v.strip() for h, v in zip(header, row)})
    return out, None


def mask(text: str | None, secrets: set[str]) -> str | None:
    if not text:
        return text
    # longest first, so a secret containing another is hidden whole
    for s in sorted(secrets, key=len, reverse=True):
        text = text.replace(s, MASK)
    return text
