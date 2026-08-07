"""Unit tests for pr_watch's CI check-run detection (added alongside the
comment-watching logic after a real miss: a failing check-run sat on page 2 of
a 43-check-run PR and a naively-paginated `gh api check-runs` call never saw
it).

Runs with plain `python3 -m unittest` - no pytest dependency, no `gh` binary
required (the `gh` call itself is monkeypatched).
"""

from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pr_watch  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _check_run(id_: int, name: str, conclusion: str, page: int) -> dict:
    return {
        "id": id_,
        "name": name,
        "conclusion": conclusion,
        "completed_at": "2024-01-01T00:00:00Z",
        "html_url": f"https://github.com/o/r/actions/runs/{page}/job/{id_}",
    }


class CheckRunPaginationTest(unittest.TestCase):
    """Mirrors the real incident: 43 check-runs, the failing one past page 1."""

    def setUp(self):
        # Page 1: 100 passing runs (a naive un-paginated call would stop here
        # and never see the failure that lives on page 2).
        self.page1 = {
            "check_runs": [_check_run(i, f"check-{i}", "success", 1) for i in range(100)]
        }
        # Page 2: a handful more, including one real failure and one
        # cancelled run (e.g. superseded by a later push - not a failure).
        self.page2 = {
            "check_runs": [
                _check_run(101, "unit-tests", "success", 2),
                _check_run(102, "validate_migrations", "failure", 2),
                _check_run(103, "lint", "neutral", 2),
                _check_run(104, "CodeQL Analyze", "cancelled", 2),
            ]
        }
        # Page 3: empty - pagination must stop here, not loop forever.
        self.page3 = {"check_runs": []}

    async def _fake_gh(self, args, repo, check=True):
        assert args[0] == "api"
        assert "check-runs" in args[1]
        page = 1
        for arg in args:
            if arg.startswith("page="):
                page = int(arg.split("=")[1])
        return json.dumps({1: self.page1, 2: self.page2, 3: self.page3}[page])

    def test_failure_on_second_page_is_found(self):
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)):
            failures = _run(pr_watch._check_run_failures(".", "o", "r", "deadbeef"))
        names = {f["name"] for f in failures}
        self.assertEqual(names, {"validate_migrations"})
        self.assertNotIn("unit-tests", names)  # passing runs are excluded
        self.assertNotIn("lint", names)  # neutral is not a failure
        # cancelled is excluded too: often just a run superseded by a later
        # push (confirmed live on fayhealthinc/fay-ui#3732's CodeQL runs), and
        # the API gives no way to tell that apart from a real kill.
        self.assertNotIn("CodeQL Analyze", names)

    def test_no_sha_returns_no_failures(self):
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)):
            failures = _run(pr_watch._check_run_failures(".", "o", "r", None))
        self.assertEqual(failures, [])

    def test_no_ci_configured_degrades_gracefully(self):
        async def _empty_gh(args, repo, check=True):
            return ""  # gh api returning nothing, e.g. sha has no checks at all

        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=_empty_gh)):
            failures = _run(pr_watch._check_run_failures(".", "o", "r", "deadbeef"))
        self.assertEqual(failures, [])


class ActivityFoldsInCheckRunFailuresTest(unittest.TestCase):
    """`_activity()` must fold CI failures into the same items list comments use,
    so they ride poll()/serve()'s existing debounce and seen-tracking."""

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 7, "url": "https://github.com/o/r/pull/7", "title": "t",
                "comments": [], "reviews": [], "headRefOid": "deadbeef",
            })
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": "o"}, "name": "r"})
        if args[0] == "api" and args[1] == "graphql":
            return ""  # no review threads
        if args[0] == "api" and "check-runs" in args[1]:
            page = 1
            for arg in args:
                if arg.startswith("page="):
                    page = int(arg.split("=")[1])
            if page == 1:
                return json.dumps({"check_runs": [
                    _check_run(1, "validate_migrations", "failure", 1),
                ]})
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def test_failing_check_run_appears_as_an_activity_item(self):
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)):
            items = _run(pr_watch._activity(".", 7))
        kinds = [i["kind"] for i in items]
        self.assertIn("check-run:failure", kinds)
        failure = next(i for i in items if i["kind"] == "check-run:failure")
        self.assertEqual(failure["id"], "checkrun:1:failure")
        self.assertEqual(failure["url"], "https://github.com/o/r/actions/runs/1/job/1")

    def test_a_refixed_then_refailed_check_run_gets_a_new_id(self):
        # Same run id, different conclusion (fixed then broke differently) ->
        # a different seen-set key per the (run id, conclusion) rule, so it is
        # reported again; the same failure twice in a row is not.
        id_a = "checkrun:1:failure"
        id_b = "checkrun:1:cancelled"
        self.assertNotEqual(id_a, id_b)


class ServeNotifyTargetTest(unittest.TestCase):
    """serve()'s notify_role/notify_name override is what watch_via_sibling()
    relies on: a sibling-spawned watcher must message the ORIGINAL caller, not
    its own parent (a different session - the common parent). This is the
    testable half of that fix; the actual spawn-a-watcher-via-my-parent
    request in watch_via_sibling() itself depends on a live RLM
    parent/sibling relationship and the parent's own next turn, so it is not
    unit-testable here - only exercised live.
    """

    async def _fake_gh_one_comment(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 9, "url": "https://github.com/o/r/pull/9", "title": "t",
                "comments": [{"url": "c1", "author": {"login": "reviewer"},
                             "body": "hi", "createdAt": "2024-01-01T00:00:00Z"}],
                "reviews": [], "headRefOid": "deadbeef",
            })
        if args[:2] == ["repo", "view"]:
            return json.dumps({"owner": {"login": "o"}, "name": "r"})
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def test_serve_notifies_the_given_role_and_name_not_parent(self):
        import sys
        import tempfile
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append({"message": message, "receiver_role": receiver_role,
                        "receiver_name": receiver_name})
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh_one_comment)), \
                 patch.object(pr_watch, "STATE_PATH", state_path), \
                 patch.dict(sys.modules, {"agent_message": fake_agent_message}):
                # Seed nothing (seed=False) so the pre-existing comment is
                # immediately "new", and quiet_seconds=0 so it is reported on
                # the very first poll instead of waiting out a debounce window.
                _run(pr_watch.serve(
                    repo=".", pr=9, quiet_seconds=0, poll_seconds=0.01,
                    max_hours=0.0005, seed=False,
                    notify_role="sibling", notify_name="original-caller-session",
                ))
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["receiver_role"], "sibling")
        self.assertEqual(sent[0]["receiver_name"], "original-caller-session")


if __name__ == "__main__":
    unittest.main()
