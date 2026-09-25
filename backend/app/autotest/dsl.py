"""The scenario language: one Turkish command per line.

    Git {{ADRES}}
    Kullan "Giriş"
    Ata EPOSTA = "test+{{rastgele.sayi}}@dgpays.com"
    Yaz "E-posta" = "{{EPOSTA}}"
    Tıkla "Kaydet"
    Kaydet "css:.siparis-no" -> SIPARIS
    Eğer "Kampanya"
      Tıkla "Kapat"
    Bitti
    Tekrarla 3
      Tıkla "Sonraki"
    Bitti
    Gör "{{SIPARIS}}"

A target in quotes is what a person sees: a button's text, a field's label
or placeholder. "css:..." or "xpath:..." reaches anything else. Blank lines
and lines starting with # are ignored; indentation is only for the reader.
Commands are matched without regard to case or Turkish letters, so "tikla"
and "TIKLA" work as well.

Blocks (Tekrarla, Eğer, Eğer yoksa) end with Bitti; Eğer may have a Değilse.
"""
import re
from dataclasses import dataclass, field

# verb -> (arity, help line). Arity is how the rest of the line is read:
# an int is that many quoted arguments; the strings name special forms.
VERBS = {
    "git": ("url", 'Git https://adres — sayfayı açar'),
    "tikla": (1, 'Tıkla "Giriş Yap" — düğme, bağlantı ya da yazıya tıklar'),
    "cifttikla": (1, 'Çift tıkla "Satır" — çift tıklar'),
    "yaz": (2, 'Yaz "E-posta" = "ali@dgpays.com" — alana yazar'),
    "sec": (2, 'Seç "Ülke" = "Türkiye" — açılır listeden seçer'),
    "isaretle": (1, 'İşaretle "Beni hatırla" — kutuyu işaretler'),
    "isaretikaldir": (1, 'İşareti kaldır "Beni hatırla"'),
    "uzerinegel": (1, 'Üzerine gel "Menü" — fareyi üstüne getirir'),
    "bas": (1, 'Bas "Enter" — klavye tuşu (Enter, Tab, Escape…)'),
    "gor": (1, 'Gör "Hoş geldiniz" — yazı sayfada görünmeli'),
    "gorme": (1, 'Görme "Hata" — yazı sayfada görünmemeli'),
    "deger": (2, 'Değer "Tutar" = "100,00" — alanın içindeki değer bu olmalı'),
    "say": ("count", 'Say "css:.satir" = 5 — sayfada tam bu kadar olmalı'),
    "adres": (1, 'Adres "/hesabim" — adres bunu içermeli'),
    "bekle": ("seconds", 'Bekle 2 — saniye bekler'),
    "yenile": (0, 'Yenile — sayfayı yeniler'),
    "geri": (0, 'Geri — önceki sayfaya döner'),
    "kaydet": ("capture", 'Kaydet "css:.siparis-no" -> SIPARIS — ekrandaki değeri saklar'),
    "ata": ("assign", 'Ata EPOSTA = "test+{{rastgele.sayi}}@dgpays.com" — değişkene değer verir'),
    "kullan": (1, 'Kullan "Giriş" — başka bir senaryonun adımlarını çalıştırır'),
    "tekrarla": ("times", 'Tekrarla 3 … Bitti — aradaki adımları tekrarlar ({{tur}} kaçıncı tur)'),
    "eger": (1, 'Eğer "Kampanya" … Değilse … Bitti — yazı görünüyorsa'),
    "egeryoksa": (1, 'Eğer yoksa "Hata" … Bitti — yazı görünmüyorsa'),
    "degilse": (0, None),
    "bitti": (0, None),
}
BLOCKS = {"tekrarla", "eger", "egeryoksa"}

_FOLD = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iissgguuoocc")
QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”|\'([^\']*)\'')
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
ARROW = re.compile(r"^\s*(?:->|→|=>|=)\s*([A-Za-z_][A-Za-z0-9_]*)\s*$")


def fold(text: str) -> str:
    """Lower-case without Turkish letters: 'İşareti kaldır' -> 'isaretikaldir'."""
    return text.translate(_FOLD).lower()


@dataclass
class Step:
    line: int          # 1-based, as the editor numbers them
    text: str          # the line as written, without its indentation
    verb: str
    args: list = field(default_factory=list)
    children: list = field(default_factory=list)       # a block's body
    otherwise: list = field(default_factory=list)      # Eğer's Değilse part


@dataclass
class ParseError:
    line: int
    message: str


def _verb(head: str) -> tuple[str | None, str]:
    """Split the command word(s) off a line. Two-word commands ('Çift
    tıkla', 'İşareti kaldır', 'Eğer yoksa') are tried first."""
    words = head.split()
    for n in (2, 1):
        if len(words) >= n:
            key = fold("".join(words[:n]))
            if key in VERBS:
                return key, " ".join(head.split(maxsplit=n)[n:]) if len(words) > n else ""
    return None, head


def _usage(key: str) -> str:
    return (VERBS[key][1] or key).split(" — ")[0]


def _one(number: int, line: str) -> tuple[Step | None, ParseError | None]:
    cut = len(line)
    for mark in ('"', "“", "'"):
        at = line.find(mark)
        if at >= 0:
            cut = min(cut, at)
    head, rest = line[:cut], line[cut:]
    key, tail = _verb(head)
    if key is None:
        return None, ParseError(number, f"bilinmeyen komut: {line.split()[0]}")
    arity = VERBS[key][0]
    rest = (tail + " " + rest).strip()
    wrong = ParseError(number, f"beklenen biçim: {_usage(key)}")

    if arity == "url":
        url = rest.strip("\"'“” ")
        if not url:
            return None, ParseError(number, "Git bir adres ister: Git https://…")
        return Step(number, line, key, [url]), None
    if arity in ("seconds", "times"):
        try:
            n = float(rest.strip("\"'“” ").replace(",", ".") or "1")
        except ValueError:
            return None, wrong
        if arity == "seconds":
            if not 0 < n <= 120:
                return None, ParseError(number, "Bekle 0 ile 120 saniye arası olmalı")
            return Step(number, line, key, [n]), None
        if n != int(n) or not 1 <= n <= 100:
            return None, ParseError(number, "Tekrarla 1 ile 100 arası bir sayı ister")
        return Step(number, line, key, [int(n)]), None
    if arity == 0:
        if rest:
            return None, wrong
        return Step(number, line, key, []), None
    if arity == "assign":
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", rest)
        quoted = QUOTED.fullmatch(m.group(2).strip()) if m else None
        if not quoted:
            return None, wrong
        value = next(g for g in quoted.groups() if g is not None)
        return Step(number, line, key, [m.group(1), value]), None

    args = [next(g for g in m.groups() if g is not None) for m in QUOTED.finditer(rest)]
    after = QUOTED.sub("", rest)
    if arity == "capture":
        m = ARROW.match(after)
        if len(args) != 1 or not m:
            return None, wrong
        return Step(number, line, key, [args[0], m.group(1)]), None
    if arity == "count":
        m = re.match(r"^\s*=\s*(\d+)\s*$", after)
        if len(args) != 1 or not m:
            return None, wrong
        return Step(number, line, key, [args[0], int(m.group(1))]), None
    if len(args) != arity:
        return None, wrong
    if any(not a.strip() for a in args):
        return None, ParseError(number, "tırnak içi boş olamaz")
    return Step(number, line, key, args), None


def parse(source: str) -> tuple[list[Step], list[ParseError]]:
    """Steps as a tree: a block's body hangs under the step that opens it."""
    root: list[Step] = []
    stack: list[tuple[Step | None, list[Step]]] = [(None, root)]
    errors: list[ParseError] = []
    for number, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        step, error = _one(number, line)
        if error:
            errors.append(error)
            continue
        opener, into = stack[-1]
        if step.verb == "bitti":
            if opener is None:
                errors.append(ParseError(number, "Bitti'ye karşılık gelen bir blok yok"))
            else:
                stack.pop()
            continue
        if step.verb == "degilse":
            if opener is None or opener.verb not in ("eger", "egeryoksa") or into is opener.otherwise:
                errors.append(ParseError(number, "Değilse yalnız bir Eğer bloğunun içinde olur"))
            else:
                stack[-1] = (opener, opener.otherwise)
            continue
        into.append(step)
        if step.verb in BLOCKS:
            stack.append((step, step.children))
    for opener, _ in stack[1:]:
        errors.append(ParseError(opener.line, f"{opener.text.split()[0]} bloğu Bitti ile kapanmamış"))

    if not root and not errors:
        errors.append(ParseError(1, "senaryoda hiç adım yok"))
    return root, errors


def walk(steps: list[Step]):
    for s in steps:
        yield s
        yield from walk(s.children)
        yield from walk(s.otherwise)


def assigned(steps: list[Step]) -> set[str]:
    """Names the scenario gives a value itself, with Ata or Kaydet."""
    out = set()
    for s in walk(steps):
        if s.verb == "ata":
            out.add(s.args[0])
        elif s.verb == "kaydet":
            out.add(s.args[1])
    return out


def includes(steps: list[Step]) -> set[str]:
    return {s.args[0] for s in walk(steps) if s.verb == "kullan"}


def help_lines() -> list[str]:
    return [usage for _, usage in VERBS.values() if usage]
