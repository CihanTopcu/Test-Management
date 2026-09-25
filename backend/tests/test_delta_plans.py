"""The sync must look inside test plans for new results, not only at
standalone runs: TestRail's get_runs leaves plan runs out."""
import json
import os
import sys

MIGRATION = os.path.join(os.path.dirname(__file__), "..", "..", "migration")


class FakeTestRail:
    """Answers the handful of calls dump_delta makes for one project."""

    def __init__(self):
        self.plan_run = {"id": 501, "name": "Plan koşumu", "is_archived": False}
        self.answers = {
            "get_suites/7": [],
            "get_milestones/7": [],
            "get_plans/7": [{"id": 90, "name": "Sürüm planı"}],
            "get_runs/7": [],
            "get_results_for_run/501&created_after=100": [{"id": 9001, "test_id": 1}],
            "get_tests/501": [{"id": 1, "case_id": 11, "status_id": 5}],
            "get_results_for_run/501": [{"id": 9001, "test_id": 1, "status_id": 5}],
        }

    def all(self, path, key):
        return self.answers[path]

    def get(self, path):
        assert path == "get_plan/90", path
        return {"id": 90, "entries": [{"id": "e1", "runs": [self.plan_run]}]}


def test_a_result_in_a_plan_run_is_picked_up(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.abspath(MIGRATION))
    import delta

    raw = tmp_path / "raw"
    (raw / "meta").mkdir(parents=True)
    (raw / "meta" / "projects.json").write_text(
        json.dumps([{"id": 7, "name": "Planlı proje"}]), encoding="utf-8")
    # the run is already known, so only its new results are asked for
    (raw / "projects" / "7" / "run_501").mkdir(parents=True)
    monkeypatch.setattr(delta, "RAW", str(raw))

    manifest = delta.dump_delta(FakeTestRail(), since=100)

    assert manifest["runs"] == [501]
    saved = json.loads((raw / "projects" / "7" / "run_501" / "results.json")
                       .read_text(encoding="utf-8"))
    assert [r["id"] for r in saved] == [9001]
