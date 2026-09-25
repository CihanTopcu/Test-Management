"""The scenario language: one Turkish command per line.

    Git https://www.dgpays.com
    Tıkla "Giriş Yap"
    Yaz "E-posta" = "test@dgpays.com"
    Seç "Ülke" = "Türkiye"
    İşaretle "Beni hatırla"
    Bas "Enter"
    Gör "Hoş geldiniz"
    Görme "Hata"
    Adres "/hesabim"
    Bekle 2

A target in quotes is what a person sees: a button's text, a field's label
or placeholder. "css:..." or "xpath:..." reaches anything else. Blank lines
and lines starting with # are ignored. Commands are matched without regard
to case or Turkish letters, so "tikla" and "TIKLA" work as well.
"""
import re
from dataclasses import dataclass, field

# verb -> (canonical name, how many quoted arguments, help line)
VERBS = {
    "git": ("git", "url", 'Git https://adres — sayfayı açar'),
    "tikla": ("tikla", 1, 'Tıkla "Giriş Yap" — düğme, bağlantı ya da yazıya tıklar'),
    "cifttikla": ("cifttikla", 1, 'Çift tıkla "Satır" — çift tıklar'),
    "yaz": ("yaz", 2, 'Yaz "E-posta" = "ali@dgpays.com" — alana yazar'),
    "sec": ("sec", 2, 'Seç "Ülke" = "Türkiye" — açılır listeden seçer'),
    "isaretle": ("isaretle", 1, 'İşaretle "Beni hatırla" — kutuyu işaretler'),
    "isaretikaldir": ("isaretikaldir", 1, 'İşareti kaldır "Beni hatırla"'),
    "uzerinegel": ("uzerinegel", 1, 'Üzerine gel "Menü" — fareyi üstüne getirir'),
    "bas": ("bas", 1, 'Bas "Enter" — klavye tuşu (Enter, Tab, Escape…)'),
    "gor": ("gor", 1, 'Gör "Hoş geldiniz" — yazı sayfada görünmeli'),
    "gorme": ("gorme", 1, 'Görme "Hata" — yazı sayfada görünmemeli'),
    "adres": ("adres", 1, 'Adres "/hesabim" — adres bunu içermeli'),
    "bekle": ("bekle", "seconds", 'Bekle 2 — saniye bekler'),
}

_FOLD = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc")
QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”|\'([^\']*)\'')


def fold(text: str) -> str:
    """Lower-case without Turkish letters: 'İşareti kaldır' -> 'isaretikaldir'."""
    return text.translate(_FOLD).lower()


@dataclass
class Step:
    line: int          # 1-based, as the editor numbers them
    text: str          # the line as written
    verb: str
    args: list = field(default_factory=list)


@dataclass
class ParseError:
    line: int
    message: str


def _verb(head: str) -> tuple[str | None, str]:
    """Split the command word(s) off a line. Two-word commands ('Çift
    tıkla', 'İşareti kaldır', 'Üzerine gel') are tried first."""
    words = head.split()
    for n in (2, 1):
        if len(words) >= n:
            key = fold("".join(words[:n]))
            if key in VERBS:
                return key, " ".join(head.split(maxsplit=n)[n:]) if len(words) > n else ""
    return None, head


def parse(source: str) -> tuple[list[Step], list[ParseError]]:
    steps, errors = [], []
    for number, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # the verb is everything before the first quote or digit
        cut = len(line)
        for mark in ('"', "“", "'"):
            at = line.find(mark)
            if at >= 0:
                cut = min(cut, at)
        head, rest = line[:cut], line[cut:]
        key, tail = _verb(head)
        if key is None:
            first = line.split()[0]
            errors.append(ParseError(number, f"bilinmeyen komut: {first}"))
            continue
        _, arity, _ = VERBS[key]
        rest = (tail + " " + rest).strip()

        if arity == "url":
            url = rest.strip("\"'“” ")
            if not url:
                errors.append(ParseError(number, "Git bir adres ister: Git https://…"))
                continue
            steps.append(Step(number, line, key, [url]))
            continue
        if arity == "seconds":
            try:
                seconds = float(rest.strip("\"'“” ").replace(",", ".") or "1")
            except ValueError:
                errors.append(ParseError(number, "Bekle bir sayı ister: Bekle 2"))
                continue
            if not 0 < seconds <= 120:
                errors.append(ParseError(number, "Bekle 0 ile 120 saniye arası olmalı"))
                continue
            steps.append(Step(number, line, key, [seconds]))
            continue

        args = [next(g for g in m.groups() if g is not None) for m in QUOTED.finditer(rest)]
        if len(args) != arity:
            _, _, usage = VERBS[key]
            errors.append(ParseError(number, f"beklenen biçim: {usage.split(' — ')[0]}"))
            continue
        if any(not a.strip() for a in args):
            errors.append(ParseError(number, "tırnak içi boş olamaz"))
            continue
        steps.append(Step(number, line, key, args))

    if not steps and not errors:
        errors.append(ParseError(1, "senaryoda hiç adım yok"))
    return steps, errors


def help_lines() -> list[str]:
    return [usage for _, _, usage in VERBS.values()]
