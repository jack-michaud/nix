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
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")):
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


class RepoSlugResolutionTest(unittest.TestCase):
    """The jj-workspace bug: `gh` infers its repo from cwd's git remote, and a
    `jj workspace add` directory has no `.git`, so every gh call died with
    "failed to run git: fatal: not a git repository". serve() raised the instant
    it armed and never polled - and since a fresh PR is quiet, nothing revealed
    it. Four live watchers were lost that way."""

    def setUp(self):
        pr_watch._SLUG_CACHE.clear()

    def tearDown(self):
        pr_watch._SLUG_CACHE.clear()

    def test_falls_back_to_jj_origin_when_there_is_no_git_dir(self):
        async def _fake_run(binary, args, cwd):
            if binary == "git":
                return 128, "", ("fatal: not a git repository (or any of the "
                                 "parent directories): .git")
            # Real `jj git remote list` output from fay-service: the GitHub
            # `origin` is neither first nor the only remote.
            return 0, ("bitbucket git@bitbucket.org:fayhealthinc/fay-service.git\n"
                       "no-mistakes /Users/j/.no-mistakes/repos/0b7165a5.git\n"
                       "origin git@github.com:fayhealthinc/fay-service.git"), ""

        with patch.object(pr_watch, "_run", new=AsyncMock(side_effect=_fake_run)), \
                patch.dict(pr_watch.os.environ, {}, clear=False):
            pr_watch.os.environ.pop("GH_REPO", None)
            slug = _run(pr_watch._resolve_slug("."))
        # NOT the bitbucket remote, which is what "take the first line" gives.
        self.assertEqual(slug, "fayhealthinc/fay-service")

    def test_resolution_is_cached_per_path(self):
        calls = []

        async def _fake_run(binary, args, cwd):
            calls.append(binary)
            return 0, "https://github.com/o/r.git", ""

        with patch.object(pr_watch, "_run", new=AsyncMock(side_effect=_fake_run)):
            path = str(Path(".").resolve())
            self.assertEqual(_run(pr_watch._resolve_slug(path)), "o/r")
            self.assertEqual(_run(pr_watch._resolve_slug(path)), "o/r")
        # serve() polls every 30s for up to 6h; resolution must not reshell.
        self.assertEqual(len(calls), 1)

    def test_unresolvable_repo_fails_loudly(self):
        async def _fake_run(binary, args, cwd):
            return 128, "", "not a repo of any kind"

        with patch.object(pr_watch, "_run", new=AsyncMock(side_effect=_fake_run)):
            pr_watch.os.environ.pop("GH_REPO", None)
            with self.assertRaises(pr_watch.PrWatchError) as ctx:
                _run(pr_watch._resolve_slug("."))
        # The whole point: a watcher must never look armed while being dead.
        self.assertIn("cannot determine the GitHub repo", str(ctx.exception))

    def test_non_github_origin_is_rejected(self):
        self.assertIsNone(
            pr_watch._parse_github_url("git@bitbucket.org:fayhealthinc/fay-service.git"))
        self.assertEqual(
            pr_watch._parse_github_url("git@github.com:o/r.git"), "o/r")
        self.assertEqual(
            pr_watch._parse_github_url("https://github.com/o/r"), "o/r")
        self.assertEqual(
            pr_watch._parse_github_url("ssh://git@github.com/o/r.git"), "o/r")


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
                 patch.object(pr_watch, "EVENTS_PATH", Path(tmp) / "events.jsonl"), \
                 patch.object(pr_watch, "_resolve_slug",
                              new=AsyncMock(return_value="o/r")), \
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


class IgnoreSignaturesTest(unittest.TestCase):
    """Every agent authenticates as `jack-michaud`, so the trailing `-- <Name>`
    signature - not the author - is what marks a comment as an agent's own."""

    def _item(self, body, kind="comment"):
        return {"kind": kind, "id": "x", "author": "jack-michaud", "body": body}

    def test_no_signatures_listed_filters_nothing(self):
        self.assertFalse(pr_watch._has_ignored_signature(
            self._item("anything at all\n\n-- Kalinda"), ()))

    def test_agent_signature_on_the_last_line_is_filtered(self):
        self.assertTrue(pr_watch._has_ignored_signature(
            self._item("Heads up, I pushed a fix.\n\n-- Kalinda"), ["Kalinda"]))

    def test_unsigned_human_comment_is_not_filtered(self):
        self.assertFalse(pr_watch._has_ignored_signature(
            self._item("this needs a test"), ["Kalinda"]))

    def test_a_comment_that_merely_quotes_a_signature_is_not_filtered(self):
        body = ("Kalinda wrote:\n\n> done\n> -- Kalinda\n\n"
                "...but that is not what I asked for.")
        self.assertFalse(pr_watch._has_ignored_signature(
            self._item(body), ["Kalinda"]))

    def test_a_merge_item_with_a_none_body_is_never_filtered(self):
        # The case that would silently eat the notification the merge detection
        # exists to produce: a lifecycle item has no body to sign, and
        # `body=None` must not be read as "the last line is a signature".
        for kind in sorted(pr_watch.LIFECYCLE_KINDS):
            self.assertFalse(
                pr_watch._has_ignored_signature(
                    {"kind": kind, "id": f"{kind}:1", "author": None,
                     "body": None},
                    ["Kalinda"]),
                f"{kind} must never be signature-suppressed")

    def test_a_lifecycle_item_is_not_filtered_even_if_its_body_looks_signed(self):
        self.assertFalse(pr_watch._has_ignored_signature(
            {"kind": "merged", "id": "merged:abc", "author": None,
             "body": "merged as abc\n\n-- Kalinda"}, ["Kalinda"]))

    def test_a_check_run_item_with_no_body_is_never_filtered(self):
        self.assertFalse(pr_watch._has_ignored_signature(
            {"kind": "check-run:failure", "id": "checkrun:1:failure",
             "author": None, "body": None}, ["Kalinda"]))

    def test_two_signatures_at_once(self):
        self.assertTrue(pr_watch._has_ignored_signature(
            self._item("ack\n-- Bashaarat"), ["Kalinda", "Bashaarat"]))
        self.assertTrue(pr_watch._has_ignored_signature(
            self._item("ack\n-- Kalinda"), ["Kalinda", "Bashaarat"]))
        self.assertFalse(pr_watch._has_ignored_signature(
            self._item("ack\n-- Nat"), ["Kalinda", "Bashaarat"]))

    def test_matching_is_case_sensitive(self):
        self.assertFalse(pr_watch._has_ignored_signature(
            self._item("ack\n-- kalinda"), ["Kalinda"]))


class ServeIgnoresSignedItemsTest(unittest.TestCase):
    """A signed item must not be notified, must not count toward the "N new
    item(s)" total, and must still be marked seen."""

    def _comments(self):
        return [
            {"url": "c1", "author": {"login": "jack-michaud"},
             "body": "Watching this PR.\n\n-- Kalinda",
             "createdAt": "2024-01-01T00:00:00Z"},
            {"url": "c2", "author": {"login": "jack-michaud"},
             "body": "this needs a test",
             "createdAt": "2024-01-01T00:00:01Z"},
        ]

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 9, "url": "https://github.com/o/r/pull/9", "title": "t",
                "comments": self._comments(), "reviews": [], "headRefOid": "deadbeef",
            })
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def _serve(self, **kwargs):
        import sys
        import tempfile
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append(message)
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)),                  patch.object(pr_watch, "STATE_PATH", state_path),                  patch.object(pr_watch, "EVENTS_PATH", Path(tmp) / "events.jsonl"),                  patch.object(pr_watch, "_resolve_slug",
                              new=AsyncMock(return_value="o/r")),                  patch.dict(sys.modules, {"agent_message": fake_agent_message}):
                _run(pr_watch.serve(repo=".", pr=9, quiet_seconds=0,
                                    poll_seconds=0.01, max_hours=0.0005,
                                    seed=False, **kwargs))
                state = json.loads(state_path.read_text())
        return sent, state

    def test_default_reports_both_comments(self):
        sent, _ = self._serve()
        self.assertTrue(sent)
        self.assertIn("2 new item(s)", sent[0])
        self.assertIn("-- Kalinda", sent[0])

    def test_signed_item_is_dropped_and_not_counted(self):
        sent, state = self._serve(ignore_signatures=["Kalinda"])
        self.assertTrue(sent)
        self.assertIn("1 new item(s)", sent[0])
        self.assertIn("this needs a test", sent[0])
        self.assertNotIn("-- Kalinda", sent[0])
        seen = next(iter(state["watches"].values()))["seen"]
        self.assertIn("c1", seen)


class LifecycleItemsTest(unittest.TestCase):
    """Merge/close detection, against the real `gh pr view --json` shapes.

    Field spellings verified live rather than guessed (`gh pr view --json` on
    fayhealthinc/fay-service#7256): `state` is "MERGED", the timestamp field is
    `mergedAt` - there is NO `merged` field - and `mergeCommit` is an object
    `{"oid": "<sha>"}`, null while the PR is open.
    """

    def test_a_merged_pr_yields_a_merged_item_carrying_the_merge_sha(self):
        items = pr_watch._lifecycle_items({
            "number": 7256, "url": "https://github.com/o/r/pull/7256",
            "state": "MERGED", "isDraft": False,
            "mergedAt": "2026-08-11T19:35:42Z",
            "mergeCommit": {"oid": "de2c28ae4813baf9be7e9d21644176adf1084891"},
        })
        self.assertEqual([i["kind"] for i in items], ["merged"])
        self.assertEqual(items[0]["id"],
                         "merged:de2c28ae4813baf9be7e9d21644176adf1084891")
        self.assertIn("de2c28ae", items[0]["body"])

    def test_a_closed_unmerged_pr_yields_closed_unmerged(self):
        items = pr_watch._lifecycle_items({
            "number": 7307, "url": "https://github.com/o/r/pull/7307",
            "state": "CLOSED", "mergedAt": None, "mergeCommit": None,
            "closedAt": "2026-08-13T00:00:00Z",
        })
        self.assertEqual([i["kind"] for i in items], ["closed_unmerged"])
        self.assertEqual(items[0]["id"], "closed:7307")

    def test_an_open_pr_yields_no_lifecycle_item(self):
        self.assertEqual(pr_watch._lifecycle_items({
            "number": 7297, "state": "OPEN", "isDraft": False,
            "mergedAt": None, "mergeCommit": None}), [])

    def test_terminal_and_lifecycle_kind_sets_agree(self):
        self.assertTrue(pr_watch.TERMINAL_KINDS <= pr_watch.LIFECYCLE_KINDS)
        self.assertEqual(pr_watch.TERMINAL_KINDS, {"merged", "closed_unmerged"})


class DraftTransitionsTest(unittest.TestCase):
    """Draft flips come from timeline EVENTS, each with its own node id, not from
    the current `isDraft` boolean - a boolean has no id to dedup on, so
    draft -> ready -> draft would report at most one transition. Node ids and
    typenames are the real ones from fay-service#7292's timeline."""

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 7292, "url": "https://github.com/o/r/pull/7292",
                "title": "t", "comments": [], "reviews": [],
                "headRefOid": "deadbeef", "state": "OPEN", "isDraft": False,
                "mergedAt": None, "mergeCommit": None,
            })
        if args[0] == "api" and args[1] == "graphql":
            return json.dumps({"data": {"repository": {"pullRequest": {
                "reviewThreads": {"nodes": []},
                "timelineItems": {"nodes": [
                    {"__typename": "ConvertToDraftEvent", "id": "CTDE_abc",
                     "createdAt": "2026-08-12T16:00:00Z",
                     "actor": {"login": "jack-michaud"}},
                    {"__typename": "ReadyForReviewEvent",
                     "id": "RFRE_lADOL8Z2uM8AAAABMfkGOs8AAAAG1aO1JQ",
                     "createdAt": "2026-08-12T17:07:52Z",
                     "actor": {"login": "jack-michaud"}},
                ]}}}}})
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def test_both_draft_transitions_appear_as_distinct_items(self):
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")):
            items = _run(pr_watch._activity(".", 7292))
        by_kind = {i["kind"]: i for i in items}
        self.assertIn("converted_to_draft", by_kind)
        self.assertIn("ready_for_review", by_kind)
        # Distinct ids, so both flips ride the seen-set independently.
        self.assertNotEqual(by_kind["converted_to_draft"]["id"],
                            by_kind["ready_for_review"]["id"])
        self.assertEqual(by_kind["ready_for_review"]["author"], "jack-michaud")


class SlugKeyMigrationTest(unittest.TestCase):
    """The fay-ui#3733 bug: state keyed by local checkout path made the same PR
    watched from a jj workspace and from the canonical clone two independent
    ledgers, so ~24h of review comments stayed unseen by one of them. The key is
    now the repo slug, and legacy path-keyed entries must be MIGRATED (seen-sets
    unioned), never dropped - dropping one replays the whole PR as new."""

    def test_a_path_keyed_entry_is_moved_onto_the_slug_key(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            legacy = f"/some/jj/workspace#3733@sess-1"
            state_path.write_text(json.dumps({"watches": {legacy: {
                "repo": "/some/jj/workspace", "pr": 3733, "owner": "sess-1",
                "seen": ["c1", "c2"], "quiet_seconds": 180}}}))
            with patch.object(pr_watch, "STATE_PATH", state_path), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="fayhealthinc/fay-ui")):
                key = _run(pr_watch._migrated_key("/some/jj/workspace", 3733,
                                                  "sess-1"))
            watches = json.loads(state_path.read_text())["watches"]
        self.assertEqual(key, "fayhealthinc/fay-ui#3733@sess-1")
        self.assertNotIn(legacy, watches)          # migrated, not duplicated
        self.assertEqual(watches[key]["seen"], ["c1", "c2"])   # and not dropped

    def test_two_checkouts_of_one_pr_collapse_to_one_key_with_a_union_seen_set(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            slug_key = "fayhealthinc/fay-ui#3733@sess-1"
            state_path.write_text(json.dumps({"watches": {
                "/some/jj/workspace#3733@sess-1": {
                    "repo": "/some/jj/workspace", "pr": 3733, "owner": "sess-1",
                    "seen": ["c1"]},
                slug_key: {"repo": "/canonical/clone", "pr": 3733,
                           "owner": "sess-1", "seen": ["c2"]},
            }}))
            with patch.object(pr_watch, "STATE_PATH", state_path), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="fayhealthinc/fay-ui")):
                _run(pr_watch._migrated_key("/some/jj/workspace", 3733, "sess-1"))
            watches = json.loads(state_path.read_text())["watches"]
        self.assertEqual(list(watches), [slug_key])
        self.assertEqual(watches[slug_key]["seen"], ["c1", "c2"])


class ServeTerminatesOnMergeTest(unittest.TestCase):
    """A merge must notify exactly once, end the loop, and land in the event log.

    Before this, `_activity()` fetched no merge fields at all, so a watcher
    polling every 30s watched a PR get merged, said nothing, and spent the rest
    of its max_hours window polling a dead PR."""

    def setUp(self):
        self.polls = 0

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            self.polls += 1
            return json.dumps({
                "number": 7256, "url": "https://github.com/o/r/pull/7256",
                "title": "t", "comments": [], "reviews": [],
                "headRefOid": "deadbeef", "state": "MERGED", "isDraft": False,
                "mergedAt": "2026-08-11T19:35:42Z",
                "mergeCommit": {"oid": "de2c28ae"},
            })
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def _serve(self, **kwargs):
        import sys
        import tempfile
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append(message)
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            events_path = Path(tmp) / "events.jsonl"
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "STATE_PATH", state_path), \
                    patch.object(pr_watch, "EVENTS_PATH", events_path), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")), \
                    patch.dict(sys.modules, {"agent_message": fake_agent_message}):
                # max_hours is generous on purpose: if the merge did NOT end the
                # loop, this test would keep polling and the poll count assertion
                # below would fail rather than the test passing by luck.
                result = _run(pr_watch.serve(repo=".", pr=7256, quiet_seconds=999,
                                             poll_seconds=0.01, max_hours=0.02,
                                             seed=False, **kwargs))
            events = [json.loads(line)
                      for line in events_path.read_text().splitlines() if line]
        return result, sent, events

    def test_merge_notifies_once_and_returns_a_terminal_summary(self):
        result, sent, events = self._serve()
        self.assertEqual(len(sent), 1, sent)
        self.assertIn("merged", sent[0])
        self.assertIn("de2c28ae", sent[0])
        # quiet_seconds=999 and the merge is still reported: terminal events
        # bypass the debounce window, since nothing more can arrive.
        self.assertIn("TERMINAL", sent[0])
        self.assertIn("merged", result)
        self.assertIn("do NOT re-arm", result)
        self.assertIn("Reported in the final message", result)
        self.assertEqual(self.polls, 1)   # the loop ended on the merge poll

    def test_the_merge_is_appended_to_the_event_log(self):
        _, _, events = self._serve()
        merged = [e for e in events if e["kind"] == "merged"]
        self.assertEqual(len(merged), 1, events)
        self.assertEqual(merged[0]["repo"], "o/r")     # slug, not local path
        self.assertEqual(merged[0]["pr"], 7256)
        self.assertEqual(merged[0]["id"], "merged:de2c28ae")
        self.assertEqual(merged[0]["url"], "https://github.com/o/r/pull/7256")
        # An iso8601 stamp that actually parses - the log is meant to be
        # replayable by other tools, not just readable.
        self.assertTrue(pr_watch.datetime.fromisoformat(merged[0]["at"]))

    def test_a_merge_is_not_suppressed_by_ignore_signatures(self):
        _, sent, _ = self._serve(ignore_signatures=["Kalinda"])
        self.assertEqual(len(sent), 1)
        self.assertIn("merged", sent[0])

    def test_an_already_seen_merge_still_ends_the_watch_without_notifying(self):
        # seed=True marks the existing merge as seen, so there is nothing to
        # report - but there is also nothing left to watch.
        result, sent, _ = self._serve_seeded()
        self.assertEqual(sent, [])
        self.assertIn("Already seen when this watch started", result)
        self.assertIn("merged", result)

    def _serve_seeded(self):
        import sys
        import tempfile
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append(message)
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "STATE_PATH", Path(tmp) / "state.json"), \
                    patch.object(pr_watch, "EVENTS_PATH", Path(tmp) / "events.jsonl"), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")), \
                    patch.dict(sys.modules, {"agent_message": fake_agent_message}):
                result = _run(pr_watch.serve(repo=".", pr=7256, quiet_seconds=0,
                                             poll_seconds=0.01, max_hours=0.02,
                                             seed=True))
        return result, sent, None


class EventLogNeverRaisesTest(unittest.TestCase):
    """A logging failure must not kill a watch: the log is an aid to
    reconstruction, not a precondition for watching."""

    def test_an_unwritable_log_path_is_swallowed(self):
        with patch.object(pr_watch, "EVENTS_PATH",
                          Path("/proc/definitely/not/writable/events.jsonl")):
            pr_watch._log_event("o/r", 1, {"kind": "merged", "id": "merged:x"})

    def test_one_line_per_event_and_valid_json(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            with patch.object(pr_watch, "EVENTS_PATH", path):
                for n in range(3):
                    pr_watch._log_event("o/r", n, {"kind": "comment",
                                                   "id": f"c{n}",
                                                   "author": "reviewer",
                                                   "url": f"u{n}"})
            lines = path.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["id"] for line in lines],
                         ["c0", "c1", "c2"])


class PollTerminalDropsTheWatchTest(unittest.TestCase):
    """poll() (the heartbeat path, not the blocking serve() path) must also stop
    paying for a dead PR: report the terminal state once and remove the watch."""

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 7304, "url": "https://github.com/o/r/pull/7304",
                "title": "t", "comments": [], "reviews": [],
                "headRefOid": "deadbeef", "state": "MERGED", "isDraft": False,
                "mergedAt": "2026-08-13T00:39:56Z",
                "mergeCommit": {"oid": "cafe1234"},
            })
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def test_merged_pr_is_reported_then_unwatched(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            key = "o/r#7304@" + pr_watch._owner()
            state_path.write_text(json.dumps({"watches": {key: {
                "repo": ".", "slug": "o/r", "pr": 7304,
                "owner": pr_watch._owner(), "seen": [], "quiet_seconds": 999}}}))
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "STATE_PATH", state_path), \
                    patch.object(pr_watch, "EVENTS_PATH", Path(tmp) / "events.jsonl"), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")):
                first = _run(pr_watch.poll())
                second = _run(pr_watch.poll())
            watches = json.loads(state_path.read_text())["watches"]
        self.assertIn("merged", first)
        self.assertIn("no longer watching", first)
        self.assertEqual(watches, {})
        # And it does not keep re-reporting: the watch is gone.
        self.assertIn("nothing is being watched", second)


if __name__ == "__main__":
    unittest.main()
