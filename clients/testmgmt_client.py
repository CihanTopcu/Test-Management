"""Client for CI jobs, shaped like the TestRail one they are replacing.

The RTTS and JMeter jobs already speak TestRail's API. Rather than ask
whoever maintains them to learn a new shape, the method names and arguments
here mirror the TestRail Python binding, so most jobs change two lines: the
base URL and the credential.

    from testmgmt_client import TestManagement

    tm = TestManagement("http://test-yonetimi.dgpays.local:8080", token="tm_...")

    run = tm.add_run(project_id=3, suite_id=42, name="Nightly 2026-10-15")
    tm.add_results_for_cases(run["id"], [
        {"case_id": 15477, "status_id": 1, "elapsed": "12s"},
        {"case_id": 15478, "status_id": 5, "defects": "JIRA-123"},
    ])
    tm.close_run(run["id"])

Status ids are the ones imported from TestRail and unchanged:
    1 Passed   2 Blocked   3 Untested   4 Retouch   5 Failed
    6 Aborted  7 Cancelled 8 Testing    9 NoRun    10 Deferred
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


class TestManagementError(Exception):
    def __init__(self, status: int, body: str, path: str):
        self.status, self.body, self.path = status, body, path
        super().__init__(f"{status} on {path}: {body}")


class TestManagement:
    """Minimal, dependency-free so it drops into any build agent."""

    def __init__(self, base_url: str, token: str, timeout: int = 60,
                 retries: int = 3):
        self.base = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.retries = retries

    # --- plumbing --------------------------------------------------------
    def _call(self, method: str, path: str, payload: Any = None) -> Any:
        url = f"{self.base}/api/{path.lstrip('/')}"
        data = json.dumps(payload).encode() if payload is not None else None
        delay = 2.0

        for attempt in range(self.retries):
            request = urllib.request.Request(url, data=data, method=method)
            request.add_header("Authorization", f"Bearer {self.token}")
            request.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as r:
                    body = r.read().decode("utf-8")
                    return json.loads(body) if body else None
            except urllib.error.HTTPError as e:
                text = e.read().decode("utf-8", "replace")[:400]
                # a build should not fail because the server was restarting
                if e.code in (502, 503, 504) and attempt < self.retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise TestManagementError(e.code, text, path) from None
            except urllib.error.URLError as e:
                if attempt < self.retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise TestManagementError(0, str(e.reason), path) from None
        raise TestManagementError(0, "retries exhausted", path)

    def get(self, path: str) -> Any:
        return self._call("GET", path)

    def post(self, path: str, payload: Any = None) -> Any:
        return self._call("POST", path, payload if payload is not None else {})

    # --- reading ---------------------------------------------------------
    def get_projects(self) -> list[dict]:
        return self.get("projects")

    def get_suites(self, project_id: int) -> list[dict]:
        return self.get(f"projects/{project_id}/suites")

    def get_cases(self, suite_id: int, section_id: int | None = None,
                  limit: int = 250) -> list[dict]:
        query = f"suites/{suite_id}/cases?limit={limit}"
        if section_id:
            query += f"&section_id={section_id}"
        return self.get(query)["items"]

    def get_runs(self, project_id: int, archived: bool = False) -> list[dict]:
        return self.get(f"projects/{project_id}/runs?archived={str(archived).lower()}")

    def get_tests(self, run_id: int, limit: int = 1000) -> list[dict]:
        # the endpoint returns a page envelope; callers want the rows
        return self.get(f"runs/{run_id}/tests?limit={limit}")["items"]

    def get_run_summary(self, run_id: int) -> dict:
        return self.get(f"runs/{run_id}/summary")

    # --- writing ---------------------------------------------------------
    def add_run(self, project_id: int, suite_id: int, name: str,
                description: str | None = None, milestone_id: int | None = None,
                assignedto_id: int | None = None, include_all: bool = True,
                case_ids: list[int] | None = None,
                section_ids: list[int] | None = None) -> dict:
        return self.post(f"projects/{project_id}/runs", {
            "suite_id": suite_id, "name": name, "description": description,
            "milestone_id": milestone_id, "assignedto_id": assignedto_id,
            "include_all": include_all, "case_ids": case_ids or [],
            "section_ids": section_ids or [],
        })

    def add_results_for_cases(self, run_id: int, results: list[dict]) -> dict:
        """Post many results in one call, addressed by case id.

        Same name and shape as TestRail's, including the behaviour that a
        case not in the run is skipped rather than failing the batch -- a
        nightly job should not lose 400 good results because one case was
        moved out of the suite. The skipped ids come back in the response.
        """
        return self.post(f"runs/{run_id}/results", {"results": results})

    def add_result_for_case(self, run_id: int, case_id: int, status_id: int,
                            **fields) -> dict:
        return self.add_results_for_cases(
            run_id, [{"case_id": case_id, "status_id": status_id, **fields}])

    def set_status_for_tests(self, run_id: int, test_ids: list[int],
                             status_id: int, comment: str | None = None) -> dict:
        return self.post(f"runs/{run_id}/bulk-status", {
            "test_ids": test_ids, "status_id": status_id, "comment": comment})

    def close_run(self, run_id: int) -> dict:
        return self._call("PATCH", f"runs/{run_id}", {"is_completed": True})

    # --- convenience -----------------------------------------------------
    def run_from_results(self, project_id: int, suite_id: int, name: str,
                         results: list[dict], close: bool = True) -> dict:
        """Create a run, post everything, close it: the whole nightly shape
        in one call."""
        run = self.add_run(project_id, suite_id, name)
        report = self.add_results_for_cases(run["id"], results)
        if close:
            self.close_run(run["id"])
        return {"run_id": run["id"], "url": f"{self.base}/#/p/{project_id}"
                                            f"/runs/{run['id']}", **report}


STATUS = {
    "passed": 1, "blocked": 2, "untested": 3, "retouch": 4, "failed": 5,
    "aborted": 6, "cancelled": 7, "testing": 8, "norun": 9, "deferred": 10,
}
