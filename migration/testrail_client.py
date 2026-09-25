"""Minimal TestRail API v2 client: pooled, throttled, retrying.

Connection reuse matters more than it looks here. The per-case phases issue
roughly 64k requests each, and without keep-alive every one of them pays for a
fresh TCP and TLS handshake -- which measured out at about three times the
cost of the request itself. One requests.Session per worker thread fixes that.
"""
import base64
import os
import threading
import time

import requests


def load_env(path=".env"):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class TestRailError(Exception):
    def __init__(self, code, body, path):
        self.code, self.body, self.path = code, body, path
        super().__init__(f"{code} on {path}: {body}")


class TestRail:
    def __init__(self, url=None, user=None, key=None, min_interval=0.15):
        env = load_env()
        self.base = (url or env.get("TESTRAIL_URL")).rstrip("/") + "/index.php?/api/v2/"
        user = user or env.get("TESTRAIL_USER")
        key = key or env.get("TESTRAIL_KEY")
        self.auth = base64.b64encode(f"{user}:{key}".encode()).decode()
        self.min_interval = min_interval
        self._last = 0.0
        self._lock = threading.Lock()
        self._local = threading.local()
        self.calls = 0
        self.throttled = 0

    # --- plumbing --------------------------------------------------------
    @property
    def session(self):
        s = getattr(self._local, "session", None)
        if s is None:
            s = requests.Session()
            s.headers.update({
                "Authorization": "Basic " + self.auth,
                "Content-Type": "application/json",
            })
            # one connection per thread is enough; the pool is per session
            s.mount("https://", requests.adapters.HTTPAdapter(
                pool_connections=2, pool_maxsize=4, max_retries=0))
            self._local.session = s
        return s

    def _throttle(self):
        with self._lock:
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            self.calls += 1

    # --- requests --------------------------------------------------------
    def get(self, path, retries=5):
        """GET an API method and parse the JSON body."""
        url = self.base + path
        delay = 2.0
        for attempt in range(retries):
            self._throttle()
            try:
                r = self.session.get(url, timeout=90)
            except requests.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise TestRailError("net", str(e), path)

            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                self.throttled += 1
                time.sleep(float(r.headers.get("Retry-After", 10)))
                continue
            # TestRail briefly 401s after a burst of failed auth; back off.
            # 504 is the gateway giving up on a slow query -- it cost sync #4
            # its whole pass on a single get_cases page -- and is as
            # transient as the 502/503 beside it.
            if r.status_code in (401, 409, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise TestRailError(r.status_code, r.text[:300], path)
        raise TestRailError("retries", "exhausted", path)

    def get_binary(self, path, dest, retries=4):
        url = self.base + path
        for attempt in range(retries):
            self._throttle()
            try:
                with self.session.get(url, timeout=180, stream=True) as r:
                    if r.status_code == 429:
                        self.throttled += 1
                        time.sleep(float(r.headers.get("Retry-After", 10)))
                        continue
                    if r.status_code != 200:
                        raise TestRailError(r.status_code, r.text[:200], path)
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                return True
            except requests.RequestException:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        return False

    # --- pagination ------------------------------------------------------
    def all(self, path, key, limit=250):
        """Walk a paginated collection and return the whole list.

        TestRail answers either with a bare list (older endpoints) or with
        {offset, limit, size, _links, <key>: [...]}.
        """
        out, offset = [], 0
        while True:
            data = self.get(f"{path}&limit={limit}&offset={offset}")
            if isinstance(data, list):
                return data
            chunk = data.get(key, [])
            out += chunk
            if not chunk or not (data.get("_links") or {}).get("next"):
                return out
            offset += len(chunk)
