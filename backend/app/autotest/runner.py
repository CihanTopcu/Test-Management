"""Run a scenario in a real browser.

Started by the API as its own process (python -m app.autotest.runner <id>),
so a hung page or a crashed browser takes down the run and nothing else.
Progress is written to the auto_runs row after every step; the page polls
it. A screenshot is kept per step under <storage_dir>/autotest/<run id>/.
"""
import os
import sys
import time
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from urllib.parse import urljoin

from . import variables
from .dsl import Step, parse


class StepFailed(Exception):
    """A step that did not hold; the message is shown to the tester as is."""


class Stopped(Exception):
    pass


# --- finding things the way a person names them ------------------------------

def _explicit(page, target: str):
    low = target.lower()
    if low.startswith("css:"):
        return page.locator(target[4:].strip())
    if low.startswith("xpath:"):
        return page.locator("xpath=" + target[6:].strip())
    return None


def _candidates(page, kind: str, target: str):
    """Ways to read `target`, most specific first. A button called "Giriş"
    should win over a paragraph that happens to contain the word."""
    explicit = _explicit(page, target)
    if explicit is not None:
        return [explicit]
    if kind == "click":
        return [
            page.get_by_role("button", name=target, exact=True),
            page.get_by_role("link", name=target, exact=True),
            page.get_by_role("tab", name=target, exact=True),
            page.get_by_role("menuitem", name=target, exact=True),
            page.get_by_role("button", name=target),
            page.get_by_role("link", name=target),
            page.get_by_label(target, exact=True),
            page.get_by_text(target, exact=True),
            page.get_by_title(target),
            page.get_by_alt_text(target),
            page.get_by_text(target),
        ]
    if kind == "field":
        return [
            page.get_by_label(target, exact=True),
            page.get_by_placeholder(target, exact=True),
            page.get_by_role("textbox", name=target),
            page.get_by_role("searchbox", name=target),
            page.get_by_role("spinbutton", name=target),
            page.get_by_role("combobox", name=target),
            page.get_by_label(target),
            page.get_by_placeholder(target),
            page.locator(f'[name="{target}"]'),
        ]
    if kind == "select":
        return [
            page.get_by_label(target, exact=True),
            page.get_by_role("combobox", name=target),
            page.get_by_label(target),
            page.locator(f'select[name="{target}"]'),
        ]
    if kind == "check":
        return [
            page.get_by_role("checkbox", name=target),
            page.get_by_role("radio", name=target),
            page.get_by_role("switch", name=target),
            page.get_by_label(target),
        ]
    if kind == "text":
        return [page.get_by_text(target, exact=True), page.get_by_text(target)]
    if kind == "any":
        return _candidates(page, "field", target) + _candidates(page, "text", target)
    raise ValueError(kind)


def find(page, kind: str, target: str, timeout: float):
    """The first visible match, waiting up to `timeout` seconds for one."""
    deadline = time.monotonic() + timeout
    while True:
        for loc in _candidates(page, kind, target):
            try:
                count = min(loc.count(), 10)
                for i in range(count):
                    item = loc.nth(i)
                    if item.is_visible():
                        return item
            except Exception:                           # noqa: BLE001
                # a detached node mid-navigation; the next round sees the new page
                continue
        if time.monotonic() >= deadline:
            raise StepFailed(f'"{target}" sayfada bulunamadı ({timeout:g} sn beklendi)')
        time.sleep(0.2)


def visible_text(page, target: str) -> bool:
    for loc in _candidates(page, "text", target):
        try:
            for i in range(min(loc.count(), 10)):
                if loc.nth(i).is_visible():
                    return True
        except Exception:                               # noqa: BLE001
            continue
    return False


# --- the commands --------------------------------------------------------------

def run_step(page, step: Step, timeout: float, values: dict | None = None) -> str | None:
    """Carry out one plain (non-block) step. Returns a short note worth
    showing, or None. Ata and Kaydet write into `values`."""
    v, a = step.verb, step.args
    ms = int(timeout * 1000)
    if values is None:
        values = {}
    if v == "git":
        url = a[0]
        if not url.startswith(("http://", "https://", "file:", "data:")):
            base = page.url if page.url.startswith("http") else None
            url = urljoin(base, url) if base else "https://" + url
        response = page.goto(url, timeout=max(ms, 30000), wait_until="domcontentloaded")
        if response is not None and response.status >= 400:
            raise StepFailed(f"sayfa {response.status} döndü: {url}")
        return page.title() or None
    if v == "tikla":
        find(page, "click", a[0], timeout).click(timeout=ms)
    elif v == "cifttikla":
        find(page, "click", a[0], timeout).dblclick(timeout=ms)
    elif v == "uzerinegel":
        find(page, "click", a[0], timeout).hover(timeout=ms)
    elif v == "yaz":
        find(page, "field", a[0], timeout).fill(a[1], timeout=ms)
    elif v == "sec":
        box = find(page, "select", a[0], timeout)
        try:
            box.select_option(label=a[1], timeout=ms)
        except Exception:                               # noqa: BLE001
            try:
                box.select_option(value=a[1], timeout=2000)
            except Exception:                           # noqa: BLE001
                raise StepFailed(f'"{a[0]}" listesinde "{a[1]}" seçeneği yok') from None
    elif v == "isaretle":
        find(page, "check", a[0], timeout).check(timeout=ms)
    elif v == "isaretikaldir":
        find(page, "check", a[0], timeout).uncheck(timeout=ms)
    elif v == "bas":
        page.keyboard.press(a[0])
    elif v == "gor":
        find(page, "text", a[0], timeout)
    elif v == "gorme":
        deadline = time.monotonic() + timeout
        while visible_text(page, a[0]):
            if time.monotonic() >= deadline:
                raise StepFailed(f'"{a[0]}" sayfada görünüyor, görünmemeliydi')
            time.sleep(0.2)
    elif v == "deger":
        box = find(page, "field", a[0], timeout)
        deadline = time.monotonic() + timeout
        while True:
            actual = box.input_value(timeout=ms)
            if actual == a[1]:
                return actual
            if time.monotonic() >= deadline:
                raise StepFailed(f'"{a[0]}" değeri "{actual}", beklenen "{a[1]}"')
            time.sleep(0.2)
    elif v == "say":
        loc = _explicit(page, a[0]) or page.get_by_text(a[0])
        deadline = time.monotonic() + timeout
        while True:
            n = loc.count()
            if n == a[1]:
                return f"{n} tane"
            if time.monotonic() >= deadline:
                raise StepFailed(f'"{a[0]}" {n} tane, beklenen {a[1]}')
            time.sleep(0.2)
    elif v == "adres":
        deadline = time.monotonic() + timeout
        while a[0] not in page.url:
            if time.monotonic() >= deadline:
                raise StepFailed(f'adres "{a[0]}" içermiyor: {page.url}')
            time.sleep(0.2)
        return page.url
    elif v == "bekle":
        page.wait_for_timeout(a[0] * 1000)
    elif v == "yenile":
        page.reload(timeout=max(ms, 30000), wait_until="domcontentloaded")
    elif v == "geri":
        page.go_back(timeout=max(ms, 30000), wait_until="domcontentloaded")
    elif v == "ata":
        values[a[0]] = a[1]
        return f"{a[0]} = {a[1]}"
    elif v == "kaydet":
        el = find(page, "any", a[0], timeout)
        tag = el.evaluate("e => e.tagName").lower()
        value = (el.input_value(timeout=ms) if tag in ("input", "textarea", "select")
                 else el.inner_text(timeout=ms)).strip()
        values[a[1]] = value
        return f"{a[1]} = {value}"
    else:
        raise StepFailed(f"desteklenmeyen komut: {v}")
    return None


MAX_INCLUDE_DEPTH = 5


class Executor:
    """Walks the step tree for one data row, logging as it goes.

    The log is built while running -- a loop or a branch decides what comes
    next -- so a step is listed when it starts. When one fails, what was
    left of the blocks it was in is listed as skipped, so the reader sees
    what did not happen.
    """

    def __init__(self, page, timeout, shots_dir, report, should_stop,
                 values, secrets, resolve_include=None, log=None, row=None):
        self.page, self.timeout, self.shots_dir = page, timeout, shots_dir
        self.report, self.should_stop = report, should_stop
        self.values, self.secrets = values, secrets
        self.resolve_include = resolve_include
        self.log = log if log is not None else []
        self.row = row

    def _entry(self, step: Step, depth: int, status: str) -> dict:
        entry = {"line": step.line, "text": step.text, "status": status, "depth": depth}
        if self.row is not None:
            entry["row"] = self.row
        self.log.append(entry)
        return entry

    def _shoot(self, entry: dict) -> None:
        if not self.shots_dir:
            return
        index = sum(1 for x in self.log if "shot" in x)
        try:
            self.page.screenshot(path=os.path.join(self.shots_dir, f"{index}.png"))
            entry["shot"] = index
        except Exception:                               # noqa: BLE001
            pass

    def _skip(self, steps: list[Step], depth: int) -> None:
        for s in steps:
            self._entry(s, depth, "skipped")

    def _fill(self, step: Step) -> Step:
        args = [variables.fill(a, self.values) if isinstance(a, str) else a for a in step.args]
        missing = [n for a in args if isinstance(a, str) for n in variables.unresolved(a)]
        if missing:
            raise StepFailed("tanımsız değişken: " + ", ".join(sorted(set(missing))))
        return Step(step.line, step.text, step.verb, args)

    def _finish(self, entry, began, note=None, error=None):
        entry["ms"] = int((time.monotonic() - began) * 1000)
        if note:
            entry["note"] = variables.mask(str(note)[:300], self.secrets)
        if error is not None:
            entry["status"] = "failed"
            entry["message"] = variables.mask(error, self.secrets)
        elif entry["status"] == "running":
            entry["status"] = "passed"

    def block(self, steps: list[Step], depth: int = 0, includes: int = 0) -> bool:
        """True when every step held."""
        for i, step in enumerate(steps):
            if self.should_stop():
                raise Stopped()
            rest = steps[i + 1:]
            entry = self._entry(step, depth, "running")
            self.report(self.log)
            began = time.monotonic()

            if step.verb == "tekrarla":
                self._finish(entry, began, note=f"{step.args[0]} tur")
                for n in range(1, step.args[0] + 1):
                    self.values["tur"] = str(n)
                    if not self.block(step.children, depth + 1, includes):
                        self._skip(rest, depth)
                        return False
                continue

            if step.verb in ("eger", "egeryoksa"):
                try:
                    target = self._fill(step).args[0]
                except StepFailed as e:
                    self._finish(entry, began, error=str(e))
                    self._skip(rest, depth)
                    return False
                seen = self._appears(target)
                holds = seen if step.verb == "eger" else not seen
                self._finish(entry, began,
                             note="görünüyor" if seen else "görünmüyor")
                branch = step.children if holds else step.otherwise
                if not self.block(branch, depth + 1, includes):
                    self._skip(rest, depth)
                    return False
                continue

            if step.verb == "kullan":
                try:
                    name = self._fill(step).args[0]
                    if includes >= MAX_INCLUDE_DEPTH:
                        raise StepFailed("Kullan çok derin (senaryolar birbirini çağırıyor olabilir)")
                    if self.resolve_include is None:
                        raise StepFailed("Kullan burada desteklenmiyor")
                    sub = self.resolve_include(name)
                except StepFailed as e:
                    self._finish(entry, began, error=str(e))
                    self._skip(rest, depth)
                    return False
                self._finish(entry, began, note=f"{len(sub)} adım")
                if not self.block(sub, depth + 1, includes + 1):
                    self._skip(rest, depth)
                    return False
                continue

            note = error = None
            try:
                note = run_step(self.page, self._fill(step), self.timeout, self.values)
            except StepFailed as e:
                error = str(e)
            except Exception as e:                      # noqa: BLE001
                error = _plain(e)
            self._finish(entry, began, note=note, error=error)
            self._shoot(entry)
            self.report(self.log)
            if error is not None:
                self._skip(rest, depth)
                return False
        return True

    def _appears(self, target: str) -> bool:
        """For Eğer: a short wait, since the thing may be on its way."""
        deadline = time.monotonic() + min(self.timeout, 2)
        while True:
            if visible_text(self.page, target):
                return True
            loc = _explicit(self.page, target)
            if loc is not None:
                try:
                    if loc.count() and loc.first.is_visible():
                        return True
                except Exception:                       # noqa: BLE001
                    pass
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.2)


def execute(page, steps: list[Step], timeout: float, shots_dir: str | None,
            report: Callable[[list[dict]], None],
            should_stop: Callable[[], bool] = lambda: False,
            values: dict[str, str] | None = None,
            secrets: set[str] | None = None,
            resolve_include: Callable[[str], list[Step]] | None = None) -> str:
    """Run one pass of the steps. Returns passed, failed or stopped.

    {{NAME}} placeholders are filled just before a step runs; the log keeps
    the step as written, and anything a secret value could leak into (a
    message, a note) is masked."""
    ex = Executor(page, timeout, shots_dir, report, should_stop,
                  dict(values or {}), secrets or set(), resolve_include)
    try:
        ok = ex.block(steps)
    except Stopped:
        report(ex.log)
        return "stopped"
    report(ex.log)
    return "passed" if ok else "failed"


def _plain(e: Exception) -> str:
    """Playwright's messages carry a call log; the first line is the point."""
    text = str(e).strip().splitlines()
    first = text[0] if text else type(e).__name__
    if "Timeout" in first:
        return "zaman aşımı: " + first
    if "net::ERR_NAME_NOT_RESOLVED" in first:
        return "adres çözümlenemedi (DNS): " + first
    return first[:400]


# --- the process the API starts ------------------------------------------------

def main(run_id: int) -> int:
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select

    from ..config import get_settings
    from ..db import SessionLocal
    from ..models import AutoRun, AutoScenario

    settings = get_settings()
    now = lambda: datetime.now(timezone.utc)                # noqa: E731

    with SessionLocal() as session:
        run = session.get(AutoRun, run_id)
        if run is None or run.status != "queued":
            return 1
        if run.stop_requested:
            # stopped while it waited its turn in a batch
            run.status, run.finished_on = "stopped", now()
            session.commit()
            return 0
        run.status, run.started_on = "running", now()
        session.commit()
        steps, errors = parse(run.steps)
        scenario = session.get(AutoScenario, run.scenario_id)
        values, secrets, broken = variables.load(session, scenario.project_id)
        rows, data_error = variables.parse_data(scenario.data)
        problems = [f"{e.line}. satır: {e.message}" for e in errors]
        if data_error:
            problems.append(data_error)
        if broken & variables.referenced(run.steps):
            problems.append("gizli değer okunamadı, yeniden girin: "
                            + ", ".join(sorted(broken)))
        if problems:
            run.status, run.finished_on = "error", now()
            run.message = "; ".join(problems)
            session.commit()
            return 1

        def resolve_include(name: str) -> list[Step]:
            other = session.scalar(select(AutoScenario).where(
                AutoScenario.project_id == scenario.project_id, AutoScenario.name == name))
            if other is None:
                raise StepFailed(f'"{name}" adında bir senaryo yok')
            sub, sub_errors = parse(other.steps)
            if sub_errors:
                e = sub_errors[0]
                raise StepFailed(f'"{name}" senaryosunda hata: {e.line}. satır: {e.message}')
            return sub

        shots = os.path.join(settings.storage_dir, "autotest", str(run_id))
        os.makedirs(shots, exist_ok=True)
        log: list[dict] = []

        def report(_=None):
            run.log = [dict(x) for x in log]
            session.commit()

        def should_stop():
            session.refresh(run, ["stop_requested"])
            return run.stop_requested

        outcome = "passed"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.autotest_headless,
                                            slow_mo=settings.autotest_slow_mo_ms)
                for n, row in enumerate(rows or [None], 1):
                    # a clean browser per data row: no cookies or login left
                    # over from the row before
                    context = browser.new_context(viewport={"width": 1366, "height": 800},
                                                  locale="tr-TR")
                    page = context.new_page()
                    row_values = dict(values)
                    if row is not None:
                        row_values.update(row)
                        row_values["satir"] = str(n)
                        shown = ", ".join(f"{k}={v}" for k, v in row.items())
                        log.append({"kind": "row", "row": n, "status": "passed", "depth": 0,
                                    "line": 0, "text": f"Veri satırı {n}: "
                                    + (variables.mask(shown, secrets) or "")})
                    ex = Executor(page, settings.autotest_step_timeout_s, shots, report,
                                  should_stop, row_values, secrets, resolve_include,
                                  log=log, row=n if row is not None else None)
                    try:
                        ok = ex.block(steps)
                    except Stopped:
                        outcome = "stopped"
                        context.close()
                        break
                    if not ok:
                        outcome = "failed"
                        if row is not None:
                            log[[i for i, x in enumerate(log) if x.get("kind") == "row"][-1]]["status"] = "failed"
                    report()
                    if not settings.autotest_headless and n == len(rows or [None]):
                        # leave the last screen up long enough to be seen
                        page.wait_for_timeout(1500)
                    context.close()
                browser.close()
            run.status = outcome
        except Exception as e:                          # noqa: BLE001
            traceback.print_exc()
            run.status = "error"
            run.message = _plain(e)
        run.log = [dict(x) for x in log]
        run.finished_on = now()
        if run.test_id and run.status in ("passed", "failed"):
            try:
                write_result(session, run, shots)
            except Exception as e:                      # noqa: BLE001
                traceback.print_exc()
                run.message = f"sonuç teste yazılamadı: {_plain(e)}"
        session.commit()
    return 0


STEP_STATUS = {"passed": 1, "failed": 5, "skipped": 3, "pending": 3, "running": 3}


def write_result(session, run, shots_dir: str) -> None:
    """Record the outcome on the test the run was started from, the way a
    tester would have: a status, a comment saying what happened, the steps
    one by one, and the screenshot of the step that failed (or of the last
    one)."""
    import hashlib
    import secrets as _secrets
    import shutil

    from ..config import get_settings
    from ..models import Attachment, Result, ResultStep, Run, Test

    test = session.get(Test, run.test_id)
    if test is None:
        return
    owner = session.get(Run, test.run_id)
    if owner is not None and owner.is_archived:
        run.message = "koşum arşivlendiği için sonuç teste yazılmadı"
        return
    log = run.log or []
    steps = [x for x in log if x.get("kind") != "row"]
    rows = [x for x in log if x.get("kind") == "row"]
    failed = next((x for x in steps if x.get("status") == "failed"), None)
    passed = sum(1 for x in steps if x.get("status") == "passed")
    seconds = int((run.finished_on - run.started_on).total_seconds()) if run.started_on else 0
    lines = [f"Otomasyon koşumu #{run.id}: {passed}/{len(steps)} adım geçti."]
    if rows:
        ok_rows = sum(1 for x in rows if x.get("status") == "passed")
        lines.append(f"Veri seti: {ok_rows}/{len(rows)} satır geçti.")
    if failed:
        where = f"{failed['row']}. veri satırı, " if failed.get("row") else ""
        lines.append(f"Kalan adım ({where}{failed['line']}. satır): {failed['text']}")
        lines.append(failed.get("message") or "")
    result = Result(test_id=test.id, status_id=1 if run.status == "passed" else 5,
                    created_by=run.started_by, created_on=run.finished_on,
                    comment="\n".join(l for l in lines if l),
                    elapsed=f"{seconds}s" if seconds else None, custom={})
    session.add(result)
    session.flush()
    for i, x in enumerate(log):
        indent = "  " * (x.get("depth") or 0)
        session.add(ResultStep(result_id=result.id, idx=i, content=indent + (x.get("text") or ""),
                               actual=x.get("message") or x.get("note"),
                               status_id=STEP_STATUS.get(x.get("status"), 3)))
    shot = failed if failed else (log[-1] if log else None)
    if shot is not None and shot.get("shot") is not None:
        src = os.path.join(shots_dir, f"{shot['shot']}.png")
        if os.path.isfile(src):
            raw = open(src, "rb").read()
            digest = hashlib.sha256(raw).hexdigest()
            key = f"{digest[:2]}/{digest}"
            dest = os.path.join(get_settings().storage_dir, key)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if not os.path.exists(dest):
                shutil.copyfile(src, dest)
            session.add(Attachment(
                testrail_id=f"u{_secrets.token_hex(12)}", entity_type="result",
                entity_id=result.id, filename=f"otomasyon-{run.id}-adim-{shot['line']}.png",
                size=len(raw), content_type="image/png", storage_key=key,
                checksum_sha256=digest, is_inline=False,
                project_id=owner.project_id if owner else None,
                created_by=run.started_by, created_on=run.finished_on))
    test.status_id = result.status_id
    run.result_id = result.id


if __name__ == "__main__":
    # several ids: a batch from a run, one browser at a time, in order
    for arg in sys.argv[1:]:
        main(int(arg))
    raise SystemExit(0)
