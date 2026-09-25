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

def run_step(page, step: Step, timeout: float) -> str | None:
    """Carry out one step. Returns a short note worth showing, or None."""
    v, a = step.verb, step.args
    ms = int(timeout * 1000)
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
    elif v == "adres":
        deadline = time.monotonic() + timeout
        while a[0] not in page.url:
            if time.monotonic() >= deadline:
                raise StepFailed(f'adres "{a[0]}" içermiyor: {page.url}')
            time.sleep(0.2)
        return page.url
    elif v == "bekle":
        page.wait_for_timeout(a[0] * 1000)
    else:
        raise StepFailed(f"desteklenmeyen komut: {v}")
    return None


def execute(page, steps: list[Step], timeout: float, shots_dir: str | None,
            report: Callable[[list[dict]], None],
            should_stop: Callable[[], bool] = lambda: False,
            values: dict[str, str] | None = None,
            secrets: set[str] | None = None) -> str:
    """Run the steps in order, reporting the log after each one.
    Returns passed, failed or stopped.

    {{NAME}} placeholders are filled from `values` just before a step runs;
    the log keeps the step as written, and anything a secret value could
    leak into (a message, a note) is masked."""
    values, secrets = values or {}, secrets or set()
    log = [{"line": s.line, "text": s.text, "status": "pending"} for s in steps]
    report(log)
    outcome = "passed"
    for i, step in enumerate(steps):
        if should_stop():
            outcome = "stopped"
            break
        entry = log[i]
        entry["status"] = "running"
        report(log)
        began = time.monotonic()
        filled = Step(step.line, step.text, step.verb,
                      [variables.fill(a, values) if isinstance(a, str) else a
                       for a in step.args])
        try:
            note = run_step(page, filled, timeout)
            entry["status"] = "passed"
            if note:
                entry["note"] = note[:300]
        except StepFailed as e:
            entry["status"] = "failed"
            entry["message"] = str(e)
        except Exception as e:                          # noqa: BLE001
            entry["status"] = "failed"
            entry["message"] = _plain(e)
        entry["ms"] = int((time.monotonic() - began) * 1000)
        for key in ("message", "note"):
            if key in entry:
                entry[key] = variables.mask(entry[key], secrets)
        if shots_dir:
            try:
                page.screenshot(path=os.path.join(shots_dir, f"{i}.png"))
                entry["shot"] = i
            except Exception:                           # noqa: BLE001
                pass
        report(log)
        if entry["status"] == "failed":
            outcome = "failed"
            break
    for entry in log:
        if entry["status"] == "pending":
            entry["status"] = "skipped"
    report(log)
    return outcome


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

    from ..config import get_settings
    from ..db import SessionLocal
    from ..models import AutoRun, AutoScenario

    settings = get_settings()
    now = lambda: datetime.now(timezone.utc)                # noqa: E731

    with SessionLocal() as session:
        run = session.get(AutoRun, run_id)
        if run is None or run.status != "queued":
            return 1
        run.status, run.started_on = "running", now()
        session.commit()
        steps, errors = parse(run.steps)
        scenario = session.get(AutoScenario, run.scenario_id)
        values, secrets, broken = variables.load(session, scenario.project_id)
        missing = sorted(variables.referenced(run.steps) - set(values))
        problems = [f"{e.line}. satır: {e.message}" for e in errors]
        if missing:
            problems.append("tanımsız değişken: " + ", ".join(missing))
        if broken & variables.referenced(run.steps):
            problems.append("gizli değer okunamadı, yeniden girin: "
                            + ", ".join(sorted(broken)))
        if problems:
            run.status, run.finished_on = "error", now()
            run.message = "; ".join(problems)
            session.commit()
            return 1

        shots = os.path.join(settings.storage_dir, "autotest", str(run_id))
        os.makedirs(shots, exist_ok=True)

        def report(log):
            run.log = [dict(x) for x in log]
            session.commit()

        def should_stop():
            session.refresh(run, ["stop_requested"])
            return run.stop_requested

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=settings.autotest_headless,
                                            slow_mo=settings.autotest_slow_mo_ms)
                page = browser.new_page(viewport={"width": 1366, "height": 800},
                                        locale="tr-TR")
                outcome = execute(page, steps, settings.autotest_step_timeout_s,
                                  shots, report, should_stop, values, secrets)
                if not settings.autotest_headless:
                    # leave the last screen up long enough to be seen
                    page.wait_for_timeout(1500)
                browser.close()
            run.status = outcome
        except Exception as e:                          # noqa: BLE001
            traceback.print_exc()
            run.status = "error"
            run.message = _plain(e)
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
    failed = next((x for x in log if x.get("status") == "failed"), None)
    passed = sum(1 for x in log if x.get("status") == "passed")
    seconds = int((run.finished_on - run.started_on).total_seconds()) if run.started_on else 0
    lines = [f"Otomasyon koşumu #{run.id}: {passed}/{len(log)} adım geçti."]
    if failed:
        lines.append(f"Kalan adım ({failed['line']}. satır): {failed['text']}")
        lines.append(failed.get("message") or "")
    result = Result(test_id=test.id, status_id=1 if run.status == "passed" else 5,
                    created_by=run.started_by, created_on=run.finished_on,
                    comment="\n".join(l for l in lines if l),
                    elapsed=f"{seconds}s" if seconds else None, custom={})
    session.add(result)
    session.flush()
    for i, x in enumerate(log):
        session.add(ResultStep(result_id=result.id, idx=i, content=x.get("text"),
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
    raise SystemExit(main(int(sys.argv[1])))
