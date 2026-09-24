"""Download every attachment binary out of TestRail into data/blobs.

The JSON dump only records that an attachment exists. The bytes themselves
live behind ``get_attachment/<id>`` and disappear with the subscription, so
this step is the one that actually rescues them.

Two sources feed it:

* ``data/raw/attachments/case_*.json`` -- files listed against a case;
* ``data/raw/attachments_inline_ids.json`` -- ids scraped out of rich-text
  fields, where an image was pasted straight into a description, a step or a
  result comment. These never appear in any attachment listing.

Resumable: a blob already on disk with the right size is not fetched again.
"""
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from urllib.parse import urlparse

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from testrail_client import TestRail, TestRailError, load_env  # noqa: E402

BASE_URL = load_env().get("TESTRAIL_URL", "").rstrip("/")
BASE_HOST = urlparse(BASE_URL).hostname or ""

RAW = os.path.join("data", "raw")
BLOBS = os.path.join("data", "blobs")
WORKERS = int(os.environ.get("BLOB_WORKERS", "8"))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

_print_lock = Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


def blob_path(att_id):
    """Shard by the first two characters; 60k files in one directory is a
    problem on Windows, and on any backup tool."""
    key = str(att_id)
    shard = key[:2].lower() or "00"
    return os.path.join(BLOBS, shard, key)


_cookie_session = None
_cookie_lock = Lock()


def cookie_session():
    """A requests session carrying a browser login cookie, if one is set.

    TESTRAIL_COOKIE in .env should hold the value of the ``tr_session``
    cookie taken from a logged-in browser. Without it the UUID attachments
    cannot be reached at all.
    """
    global _cookie_session
    with _cookie_lock:
        if _cookie_session is not None:
            return _cookie_session or None
        env = load_env()
        value = env.get("TESTRAIL_COOKIE", "").strip()
        if not value:
            _cookie_session = False
            return None
        s = requests.Session()
        s.cookies.set("tr_session", value, domain=BASE_HOST)
        s.headers.update({"User-Agent": "Mozilla/5.0"})
        _cookie_session = s
        return s


def fetch_via_cookie(item, dest):
    """Last resort for attachments the API will not serve."""
    s = cookie_session()
    if s is None:
        return False
    url = f"{BASE_URL}/index.php?/attachments/get/{item['id']}"
    try:
        r = s.get(url, timeout=120, allow_redirects=False)
    except requests.RequestException:
        return False
    # a redirect means the cookie was not accepted: it lands on /auth/login
    if r.status_code != 200 or "text/html" in r.headers.get("Content-Type", ""):
        return False
    with open(dest, "wb") as f:
        f.write(r.content)
    item["content_type"] = r.headers.get("Content-Type")
    item["via"] = "cookie"
    return True


def collect():
    """Build the work list: every attachment id we know about."""
    items = {}

    att_dir = os.path.join(RAW, "attachments")
    if os.path.isdir(att_dir):
        for fn in os.listdir(att_dir):
            if not fn.endswith(".json"):
                continue
            with open(os.path.join(att_dir, fn), encoding="utf-8") as f:
                for a in json.load(f):
                    aid = a.get("id")
                    if aid is None:
                        continue
                    items[str(aid)] = {
                        "id": str(aid),
                        "filename": a.get("name") or a.get("filename") or str(aid),
                        "size": a.get("size"),
                        "content_type": a.get("filetype") or a.get("content_type"),
                        "entity_type": "case",
                        "entity_id": a.get("case_id"),
                        "project_id": a.get("project_id"),
                        "created_by": a.get("user_id") or a.get("created_by"),
                        "created_on": a.get("created_on"),
                        "is_inline": False,
                    }

    inline_file = os.path.join(RAW, "attachments_inline_ids.json")
    if os.path.exists(inline_file):
        with open(inline_file, encoding="utf-8") as f:
            for aid in json.load(f):
                aid = str(aid)
                if aid in items:
                    items[aid]["is_inline"] = True
                else:
                    items[aid] = {
                        "id": aid, "filename": aid, "size": None,
                        "content_type": None, "entity_type": "inline",
                        "entity_id": None, "project_id": None,
                        "created_by": None, "created_on": None,
                        "is_inline": True,
                    }
    return list(items.values())


def main():
    client = TestRail(min_interval=float(os.environ.get("BLOB_INTERVAL", "0.08")))
    items = collect()
    log(f"indirilecek ek sayisi: {len(items)}")
    if not items:
        log("hic ek bulunamadi - once 'dump.py attachments' calistirin")
        return

    done = {"ok": 0, "skip": 0, "fail": 0, "bytes": 0}
    failures = []

    def fetch(item):
        dest = blob_path(item["id"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            # trust a non-empty file; sizes are re-checked in the index pass
            item["storage_key"] = os.path.relpath(dest, BLOBS).replace("\\", "/")
            item["bytes"] = os.path.getsize(dest)
            done["skip"] += 1
            return item
        try:
            client.get_binary(f"get_attachment/{item['id']}", dest)
        except (TestRailError, OSError) as e:
            # Images pasted inline get UUID ids that the API refuses with
            # "not a valid attachment" -- they are simply not in the
            # attachments table. Only the web UI serves them, and that needs
            # a browser session cookie rather than an API key.
            if not fetch_via_cookie(item, dest):
                done["fail"] += 1
                failures.append({"id": item["id"], "error": str(e)[:200]})
                item["storage_key"] = None
                return item
        item["bytes"] = os.path.getsize(dest)
        item["storage_key"] = os.path.relpath(dest, BLOBS).replace("\\", "/")
        with open(dest, "rb") as f:
            item["checksum_sha256"] = hashlib.sha256(f.read()).hexdigest()
        done["ok"] += 1
        done["bytes"] += item["bytes"]
        return item

    index = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for n, item in enumerate(pool.map(fetch, items), 1):
            index.append(item)
            if n % 500 == 0:
                log(f"  {n}/{len(items)}  indirilen={done['ok']} "
                    f"atlanan={done['skip']} hata={done['fail']} "
                    f"{done['bytes'] / 1e6:.0f} MB")

    with open(os.path.join(RAW, "attachments_index.json"), "w",
              encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    if failures:
        with open(os.path.join(RAW, "attachments_failed.json"), "w",
                  encoding="utf-8") as f:
            json.dump(failures, f, ensure_ascii=False, indent=1)

    log(f"bitti: indirilen={done['ok']} atlanan={done['skip']} "
        f"hata={done['fail']} toplam={done['bytes'] / 1e6:.1f} MB")
    if failures:
        log(f"basarisiz olanlar data/raw/attachments_failed.json icinde")


if __name__ == "__main__":
    main()
