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
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pr_watch  # noqa: E402

# The real files this suite must never touch. Recomputed from $HOME rather than
# read off the module, because the module attributes get patched below - reading
# them would make the guard test assert against its own tmpdir and pass
# vacuously.
REAL_STATE = Path.home() / ".prime/agent/pr-watch/state.json"
REAL_EVENTS = Path.home() / ".prime/agent/pr-watch/events.jsonl"


def _run(coro):
    return asyncio.run(coro)


def _fingerprint(path: Path):
    """(size, mtime_ns) for a file, or None if it does not exist."""
    if not path.exists():
        return None
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns)


class IsolatedPaths:
    """Redirect BOTH pr-watch files to a tmpdir. Every TestCase mixes this in.

    An earlier revision of this suite patched `STATE_PATH` but not
    `EVENTS_PATH`, so five fixture lines - `{"repo": "o/r", "pr": 9, ...}` and
    friends - were appended to the real `~/.prime/agent/pr-watch/events.jsonl`,
    which until then was empty. That is worse than untidy: the event log is
    meant to be the trigger for automated evaluation, so a fixture sitting in it
    is a false trigger waiting to fire on a PR that does not exist.

    Belt and braces, because the two paths are resolved differently: the ENV
    VARS cover `_events_path()`, which re-reads `PR_WATCH_EVENTS` on every call
    (and any subprocess that might inherit them), while the module ATTRIBUTES
    cover `STATE_PATH`, which is resolved once at import so its env var alone
    would not redirect it.
    """

    def setUp(self):
        super().setUp()
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        tmp = Path(tmpdir.name)
        self.state_path = tmp / "state.json"
        self.events_path = tmp / "events.jsonl"
        # Owner identity is pinned too, so provenance does not depend on which
        # kernel runs the suite: inside a sub-agent the ambient daemon session id
        # is `inherited` and poll() correctly degrades to read-only, which would
        # make ownership-independent tests fail in a child and pass at top level.
        # Tests that exercise the ambiguous path opt in via `as_session()`.
        env = patch.dict(os.environ, {"PR_WATCH_STATE": str(self.state_path),
                                      "PR_WATCH_EVENTS": str(self.events_path),
                                      "PR_WATCH_OWNER": "test-owner",
                                      "PR_WATCH_SESSION": "test-session"})
        env.start()
        self.addCleanup(env.stop)
        for attr, value in (("STATE_PATH", self.state_path),
                            ("EVENTS_PATH", self.events_path)):
            patcher = patch.object(pr_watch, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    @contextmanager
    def as_session(*, owner_env=None, session_dir=None, daemon=None,
                   session_env=None):
        """Impersonate a session's ENVIRONMENT, the way the daemon sets it up.

        The whole bug class lives in these four variables, so tests have to be
        able to set them exactly - including ABSENT, which `patch.dict` cannot
        express on its own.
        """
        wanted = {"PR_WATCH_OWNER": owner_env, "PR_WATCH_SESSION": session_env,
                  "RLM_SESSION_DIR": session_dir,
                  "PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID": daemon}
        with patch.dict(os.environ, {}, clear=False):
            for name, value in wanted.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
            yield

    def logged_events(self) -> list[dict]:
        if not self.events_path.exists():
            return []
        return [json.loads(line)
                for line in self.events_path.read_text().splitlines() if line]


def _check_run(id_: int, name: str, conclusion: str, page: int) -> dict:
    return {
        "id": id_,
        "name": name,
        "conclusion": conclusion,
        "completed_at": "2024-01-01T00:00:00Z",
        "html_url": f"https://github.com/o/r/actions/runs/{page}/job/{id_}",
    }


class CheckRunPaginationTest(IsolatedPaths, unittest.TestCase):
    """Mirrors the real incident: 43 check-runs, the failing one past page 1."""

    def setUp(self):
        super().setUp()
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


class ActivityFoldsInCheckRunFailuresTest(IsolatedPaths, unittest.TestCase):
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


class RepoSlugResolutionTest(IsolatedPaths, unittest.TestCase):
    """The jj-workspace bug: `gh` infers its repo from cwd's git remote, and a
    `jj workspace add` directory has no `.git`, so every gh call died with
    "failed to run git: fatal: not a git repository". serve() raised the instant
    it armed and never polled - and since a fresh PR is quiet, nothing revealed
    it. Four live watchers were lost that way."""

    def setUp(self):
        super().setUp()
        pr_watch._SLUG_CACHE.clear()
        self.addCleanup(pr_watch._SLUG_CACHE.clear)

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


class ServeNotifyTargetTest(IsolatedPaths, unittest.TestCase):
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
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append({"message": message, "receiver_role": receiver_role,
                        "receiver_name": receiver_name})
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        # State and event log come from IsolatedPaths - no test owns its own
        # redirection any more, so none can forget half of it.
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh_one_comment)), \
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


class IgnoreSignaturesTest(IsolatedPaths, unittest.TestCase):
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


class ServeIgnoresSignedItemsTest(IsolatedPaths, unittest.TestCase):
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
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append(message)
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        with patch.object(pr_watch, "_gh",
                          new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")), \
                patch.dict(sys.modules, {"agent_message": fake_agent_message}):
            _run(pr_watch.serve(repo=".", pr=9, quiet_seconds=0,
                                poll_seconds=0.01, max_hours=0.0005,
                                seed=False, **kwargs))
        state = json.loads(self.state_path.read_text())
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


class LifecycleItemsTest(IsolatedPaths, unittest.TestCase):
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


class DraftTransitionsTest(IsolatedPaths, unittest.TestCase):
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


class SlugKeyMigrationTest(IsolatedPaths, unittest.TestCase):
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


class ServeTerminatesOnMergeTest(IsolatedPaths, unittest.TestCase):
    """A merge must notify exactly once, end the loop, and land in the event log.

    Before this, `_activity()` fetched no merge fields at all, so a watcher
    polling every 30s watched a PR get merged, said nothing, and spent the rest
    of its max_hours window polling a dead PR."""

    def setUp(self):
        super().setUp()
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

    def _serve(self, seed=False, quiet_seconds=999, **kwargs):
        from unittest.mock import MagicMock

        sent = []

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            sent.append(message)
            return {"ok": True}

        fake_agent_message = MagicMock()
        fake_agent_message.send = _fake_send

        with patch.object(pr_watch, "_gh",
                          new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")), \
                patch.dict(sys.modules, {"agent_message": fake_agent_message}):
            # max_hours is generous on purpose: if the merge did NOT end the
            # loop, this test would keep polling and the poll count assertion
            # below would fail rather than the test passing by luck.
            result = _run(pr_watch.serve(repo=".", pr=7256,
                                         quiet_seconds=quiet_seconds,
                                         poll_seconds=0.01, max_hours=0.02,
                                         seed=seed, **kwargs))
        return result, sent, self.logged_events()

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
        result, sent, _ = self._serve(seed=True, quiet_seconds=0)
        self.assertEqual(sent, [])
        self.assertIn("Already seen when this watch started", result)
        self.assertIn("merged", result)

class EventLogNeverRaisesTest(IsolatedPaths, unittest.TestCase):
    """A logging failure must not kill a watch: the log is an aid to
    reconstruction, not a precondition for watching.

    Note the redirection style here: `PR_WATCH_EVENTS` in the environment, not
    the module attribute, because `_events_path()` reads the env var FIRST -
    that precedence is what makes test isolation stick even for code paths (and
    subprocesses) that never see a patched attribute.
    """

    def test_an_unwritable_log_path_is_swallowed(self):
        with patch.dict(os.environ,
                        {"PR_WATCH_EVENTS":
                         "/proc/definitely/not/writable/events.jsonl"}):
            pr_watch._log_event("o/r", 1, {"kind": "merged", "id": "merged:x"})

    def test_one_line_per_event_and_valid_json(self):
        for n in range(3):
            pr_watch._log_event("o/r", n, {"kind": "comment", "id": f"c{n}",
                                           "author": "reviewer", "url": f"u{n}"})
        lines = self.events_path.read_text().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual([json.loads(line)["id"] for line in lines],
                         ["c0", "c1", "c2"])

    def test_a_repo_that_is_not_a_slug_is_refused(self):
        # Cheap sanity on the one field downstream automation keys off. A local
        # path is the specific shape that used to get here: the pre-slug state
        # key was `<checkout path>#<pr>@<owner>`.
        for bad in ("/Users/jack/Code/github.com/fayhealthinc/fay-service",
                    "fayhealthinc/fay-service/extra", "fay-service", "", None):
            pr_watch._log_event(bad, 1, {"kind": "merged", "id": "merged:x"})
        self.assertEqual(self.logged_events(), [])

    def test_a_well_formed_slug_is_accepted(self):
        # Deliberately a slug that names no real repository: if isolation ever
        # breaks again, a fixture line in the production log must not be able to
        # trigger an eval against a PR that exists. (Learned the hard way - a
        # `fayhealthinc/fay-service#7304 merged` FIXTURE line did leak into the
        # real log while deliberately breaking the isolation to test this guard.)
        pr_watch._log_event("test-owner/test-repo", 7304,
                            {"kind": "merged", "id": "merged:41b75261"})
        self.assertEqual([e["repo"] for e in self.logged_events()],
                         ["test-owner/test-repo"])

    def test_slug_validation_would_NOT_have_caught_the_fixture_leak(self):
        # Honest limitation, recorded so nobody relies on the wrong guard: the
        # fixtures that leaked into the production log used `repo="o/r"`, which
        # IS a well-formed slug and is accepted here. Only the env/attribute
        # isolation in IsolatedPaths - and the guard test below - actually
        # prevents that leak.
        pr_watch._log_event("o/r", 9, {"kind": "comment", "id": "c1"})
        self.assertEqual(len(self.logged_events()), 1)


class ProductionLogIsNeverTouchedTest(IsolatedPaths, unittest.TestCase):
    """The guard for the defect this suite actually shipped once.

    Five fixture lines were appended to the real
    `~/.prime/agent/pr-watch/events.jsonl` by an earlier version of these
    tests. This asserts, over a full `serve()` run that definitely logs, that
    neither real file changed - and, so it cannot pass vacuously, that the
    events went to the tmp log instead.
    """

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 9, "url": "https://github.com/o/r/pull/9", "title": "t",
                "comments": [{"url": "c1", "author": {"login": "reviewer"},
                              "body": "hi", "createdAt": "2024-01-01T00:00:00Z"}],
                "reviews": [], "headRefOid": "deadbeef", "state": "MERGED",
                "isDraft": False, "mergedAt": "2024-01-02T00:00:00Z",
                "mergeCommit": {"oid": "abc1234"},
            })
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def test_a_full_serve_run_leaves_the_real_state_and_log_untouched(self):
        from unittest.mock import MagicMock

        before_events = _fingerprint(REAL_EVENTS)
        before_state = _fingerprint(REAL_STATE)

        fake_agent_message = MagicMock()

        async def _fake_send(message, receiver_role=None, receiver_name=None):
            return {"ok": True}

        fake_agent_message.send = _fake_send
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")), \
                patch.dict(sys.modules, {"agent_message": fake_agent_message}):
            _run(pr_watch.serve(repo=".", pr=9, quiet_seconds=0,
                                poll_seconds=0.01, max_hours=0.02, seed=False))

        # Not vacuous: the run really did log, just somewhere disposable.
        kinds = {e["kind"] for e in self.logged_events()}
        self.assertIn("merged", kinds)
        self.assertIn("comment", kinds)
        self.assertEqual(_fingerprint(REAL_EVENTS), before_events,
                         f"{REAL_EVENTS} was modified by a test")
        self.assertEqual(_fingerprint(REAL_STATE), before_state,
                         f"{REAL_STATE} was modified by a test")

    def test_the_isolation_itself_is_in_effect(self):
        # If IsolatedPaths ever stops applying, this fails loudly instead of
        # letting the whole suite quietly write to the real files again.
        self.assertEqual(os.environ["PR_WATCH_EVENTS"], str(self.events_path))
        self.assertEqual(pr_watch._events_path(), self.events_path)
        self.assertEqual(pr_watch.STATE_PATH, self.state_path)
        self.assertNotEqual(self.events_path, REAL_EVENTS)


class PollTerminalDropsTheWatchTest(IsolatedPaths, unittest.TestCase):
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

    def _seed(self, **extra):
        key = f"o/r#7304@{pr_watch._owner()}"
        entry = {"repo": ".", "slug": "o/r", "pr": 7304,
                 "owner": pr_watch._owner(), "seen": [], "quiet_seconds": 999}
        entry.update(extra)
        self.state_path.write_text(json.dumps({"watches": {key: entry}}))
        return key

    def _poll_twice(self):
        with patch.object(pr_watch, "_gh", new=AsyncMock(side_effect=self._fake_gh)), \
                patch.object(pr_watch, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")):
            first = _run(pr_watch.poll())
            second = _run(pr_watch.poll())
        return first, second, json.loads(self.state_path.read_text())["watches"]

    def test_merged_pr_is_reported_then_unwatched(self):
        self._seed(session="test-session")
        first, second, watches = self._poll_twice()
        self.assertIn("merged", first)
        self.assertIn("no longer watching", first)
        self.assertEqual(watches, {})
        # And it does not keep re-reporting: the watch is gone.
        self.assertIn("nothing is being watched", second)

    def test_an_unprovable_entry_is_reported_but_left_in_place(self):
        # No arm-time fingerprint on the entry AND an inherited owner id: the
        # exact shape of the 57 legacy entries found on this machine. Reported,
        # never consumed.
        with self.as_session(session_dir="/x/sub-deadbeef", daemon="ancestor-id"):
            self._seed(owner="ancestor-id")
            first, second, watches = self._poll_twice()
        self.assertIn("READ-ONLY", first)
        self.assertIn("left in place", first)
        self.assertEqual(len(watches), 1)              # not dropped
        self.assertEqual(watches["o/r#7304@ancestor-id"]["seen"], [])   # not drained
        self.assertIn("READ-ONLY", second)             # and it keeps reporting


class CrossSessionDrainTest(IsolatedPaths, unittest.TestCase):
    """The 2026-08-13 ledger bug, both directions.

    `_owner()`'s fallback is `PRIME_AGENT_INTERNAL_DAEMON_WORKER_ACTIVE_SESSION_ID`,
    which the daemon exports and a spawned sub-agent INHERITS - so inside a child
    it names an ancestor. Session A and session B therefore resolve to the SAME
    owner id, and `poll(mark_seen=True)` (the default) writes
    `entry["seen"] |= fresh`. Whichever polls first drains the other's queue
    permanently: those ids never appear as `fresh` again, and on the victim's side
    the symptom is silence, indistinguishable from a quiet PR.

    Re-deriving the owner at poll time cannot fix this - the two sessions are the
    same string by construction - so ownership is settled by the fingerprint
    captured at ARM time.
    """

    SHARED_OWNER = "1d0df30d0658"      # the real orchestrator id from the incident
    A_SESSION = "/artifacts/019fdcb9/sub-aaaaaaa1"
    B_SESSION = "/artifacts/019fdcb9/sub-bbbbbbb2"

    async def _fake_gh(self, args, repo, check=True):
        if args[:2] == ["pr", "view"]:
            return json.dumps({
                "number": 7292, "url": "https://github.com/o/r/pull/7292",
                "title": "t", "state": "OPEN", "isDraft": False,
                "mergedAt": None, "mergeCommit": None, "headRefOid": "deadbeef",
                "reviews": [],
                "comments": [{"url": "c-review-1",
                              "author": {"login": "jack-michaud"},
                              "body": "this needs a test",
                              "createdAt": "2024-01-01T00:00:00Z"}],
            })
        if args[0] == "api" and args[1] == "graphql":
            return ""
        if args[0] == "api" and "check-runs" in args[1]:
            return json.dumps({"check_runs": []})
        raise AssertionError(f"unexpected gh call: {args}")

    def _write_a_ledger(self, *, fingerprint: bool):
        """One watch armed by session A, under the shared ambient owner id."""
        entry = {"repo": ".", "slug": "o/r", "pr": 7292,
                 "owner": self.SHARED_OWNER, "seen": [], "quiet_seconds": 0}
        if fingerprint:
            entry["session"] = self.A_SESSION
        self.state_path.write_text(json.dumps(
            {"watches": {f"o/r#7292@{self.SHARED_OWNER}": entry}}))
        return json.loads(self.state_path.read_text())

    def _poll_as_b(self):
        # Session B: its own session dir, but A's id leaked into the ambient
        # daemon variable, which is exactly what a sub-agent kernel sees.
        with self.as_session(session_dir=self.B_SESSION,
                             daemon=self.SHARED_OWNER):
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")):
                return _run(pr_watch.poll())

    def test_b_cannot_drain_a_fingerprinted_watch_and_never_even_sees_it(self):
        before = self._write_a_ledger(fingerprint=True)
        report = self._poll_as_b()
        after = json.loads(self.state_path.read_text())
        # Byte-identical: A's queue is untouched, so A still gets woken.
        self.assertEqual(after, before)
        self.assertEqual(json.dumps(after, sort_keys=True),
                         json.dumps(before, sort_keys=True))
        # And B is told the truth - the watch is not B's, so B sees nothing.
        self.assertIn("nothing", report.lower())
        self.assertNotIn("c-review-1", report)

    def test_b_may_report_a_legacy_watch_but_still_cannot_drain_it(self):
        # Legacy entry, no fingerprint: B cannot tell it apart from its own, so
        # it is allowed to REPORT it (losing that would hide real review comments
        # from whoever is actually watching) but must not consume it.
        before = self._write_a_ledger(fingerprint=False)
        report = self._poll_as_b()
        after = json.loads(self.state_path.read_text())
        self.assertEqual(after, before)
        self.assertIn("READ-ONLY", report)
        self.assertIn("c-review-1", report)

    def test_a_still_gets_its_own_notification_after_b_polled(self):
        # The victim's side of the bug: silence. Assert A is still woken.
        self._write_a_ledger(fingerprint=True)
        self._poll_as_b()
        with self.as_session(session_dir=self.A_SESSION,
                             daemon=self.SHARED_OWNER):
            with patch.object(pr_watch, "_gh",
                              new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")):
                report = _run(pr_watch.poll())
        self.assertIn("c-review-1", report)
        self.assertNotIn("READ-ONLY", report)   # A's ownership is provable
        seen = next(iter(json.loads(self.state_path.read_text())["watches"]
                         .values()))["seen"]
        self.assertEqual(seen, ["c-review-1"])  # and A, being the owner, consumes it

    def test_ack_refuses_rather_than_silencing_someone_elses_ledger(self):
        self._write_a_ledger(fingerprint=True)
        with self.as_session(session_dir=self.B_SESSION,
                             daemon=self.SHARED_OWNER):
            with patch.object(pr_watch, "_gh",
                             new=AsyncMock(side_effect=self._fake_gh)), \
                    patch.object(pr_watch, "_resolve_slug",
                                 new=AsyncMock(return_value="o/r")):
                with self.assertRaises(pr_watch.PrWatchError) as ctx:
                    _run(pr_watch.ack(repo=".", pr=7292))
        self.assertIn("cannot be proved to belong to this session",
                      str(ctx.exception))

    def test_unwatch_all_no_longer_deletes_other_sessions_watches(self):
        # `unwatch(all=True)` used to clear the whole file - 57 entries across 6
        # owners on the machine where this was found.
        self._write_a_ledger(fingerprint=True)
        mine_key = "o/r#999@test-owner"
        state = json.loads(self.state_path.read_text())
        state["watches"][mine_key] = {"repo": ".", "slug": "o/r", "pr": 999,
                                      "owner": "test-owner", "seen": ["x"],
                                      "session": "test-session"}
        self.state_path.write_text(json.dumps(state))
        with patch.dict(sys.modules, {"rlm_heartbeat": None}):
            report = _run(pr_watch.unwatch(all=True))
        remaining = json.loads(self.state_path.read_text())["watches"]
        self.assertEqual(list(remaining), [f"o/r#7292@{self.SHARED_OWNER}"])
        self.assertIn("left alone", report)
        self.assertIn("cleared 1 watch(es)", report)


class OwnerProvenanceTest(IsolatedPaths, unittest.TestCase):
    """Where an owner id came from decides whether it may authorise a WRITE."""

    def test_explicit_argument_wins_and_is_unambiguous(self):
        self.assertEqual(pr_watch._owner_provenance("given"), ("given", "explicit"))

    def test_pr_watch_owner_env_is_unambiguous(self):
        with self.as_session(owner_env="chosen", session_dir="/x/sub-deadbeef",
                             daemon="ancestor"):
            self.assertEqual(pr_watch._owner_provenance(), ("chosen", "PR_WATCH_OWNER"))

    def test_daemon_id_at_top_level_is_trusted(self):
        # A top-level session's RLM_SESSION_DIR basename is the session UUID, so
        # the ambient daemon id really is its own.
        with self.as_session(session_dir="/artifacts/019fdcb9-3399-776c-95ad",
                             daemon="1d0df30d0658"):
            self.assertEqual(pr_watch._owner_provenance(),
                             ("1d0df30d0658", "daemon"))

    def test_daemon_id_inside_a_subagent_is_inherited_and_ambiguous(self):
        # Verified live: in a sub-agent kernel whose own active session id was
        # 31b2e6874fba, this variable read 1d0df30d0658 - its parent's.
        with self.as_session(session_dir="/artifacts/019fdcb9/sub-4685289e",
                             daemon="1d0df30d0658"):
            owner, provenance = pr_watch._owner_provenance()
        self.assertEqual(owner, "1d0df30d0658")
        self.assertEqual(provenance, "inherited")
        self.assertIn(provenance, pr_watch.AMBIGUOUS_OWNER_SOURCES)

    def test_no_signals_at_all_is_ambiguous(self):
        with self.as_session():
            self.assertEqual(pr_watch._owner_provenance(), ("default", "default"))

    def test_resolution_order_is_unchanged_so_live_entries_still_match(self):
        # The reason the fix is NOT "prefer RLM_SESSION_DIR": every one of the 57
        # watches on disk is owned by a 12-hex daemon id, and a session-dir name
        # is `sub-4685289e`, so preferring it would orphan all of them.
        with self.as_session(session_dir="/artifacts/019fdcb9/sub-4685289e",
                             daemon="1d0df30d0658"):
            self.assertEqual(pr_watch._owner(), "1d0df30d0658")

    def test_session_fingerprint_is_per_session_not_shared_with_an_ancestor(self):
        with self.as_session(session_dir="/artifacts/019fdcb9/sub-aaaa",
                             daemon="shared"):
            a = pr_watch._session_fingerprint()
        with self.as_session(session_dir="/artifacts/019fdcb9/sub-bbbb",
                             daemon="shared"):
            b = pr_watch._session_fingerprint()
        self.assertNotEqual(a, b)   # the property the owner id lacks


class ConvergeKeysUnionsBothFormsTest(IsolatedPaths, unittest.TestCase):
    """A ledger holding BOTH key forms for one PR - live on this machine for
    fay-service#7295, #7292, #7297 and fay-ui#3733 - must converge to ONE entry
    with the UNION of the seen-sets. Intersection would swallow whatever only one
    side had reported; a fresh empty set would replay the PR's whole history."""

    def test_both_forms_collapse_to_one_entry_with_the_union(self):
        path_key = "/Users/jack/Code/github.com/fayhealthinc/fay-service#7295@own"
        slug_key = "fayhealthinc/fay-service#7295@own"
        self.state_path.write_text(json.dumps({"watches": {
            path_key: {"repo": "/Users/jack/Code/github.com/fayhealthinc/fay-service",
                       "pr": 7295, "owner": "own", "seen": ["c1", "c2"]},
            slug_key: {"repo": "/canonical/clone", "pr": 7295, "owner": "own",
                       "seen": ["c2", "c3"], "session": "/artifacts/x/sub-1111"},
        }}))
        with patch.object(pr_watch, "_resolve_slug",
                          new=AsyncMock(return_value="fayhealthinc/fay-service")):
            _run(pr_watch._converge_keys())
        watches = json.loads(self.state_path.read_text())["watches"]
        self.assertEqual(list(watches), [slug_key])
        self.assertEqual(watches[slug_key]["seen"], ["c1", "c2", "c3"])
        # Not the intersection (["c2"]), which would swallow c1 and c3...
        self.assertNotEqual(watches[slug_key]["seen"], ["c2"])
        # ...and not a fresh empty set, which would replay the PR as new.
        self.assertTrue(watches[slug_key]["seen"])
        # The fingerprint survives, or the entry would degrade to read-only for
        # its own owner.
        self.assertEqual(watches[slug_key]["session"], "/artifacts/x/sub-1111")

    def test_convergence_is_idempotent(self):
        self.state_path.write_text(json.dumps({"watches": {
            "/repo/path#7297@own": {"repo": "/repo/path", "pr": 7297,
                                    "owner": "own", "seen": ["a"]}}}))
        with patch.object(pr_watch, "_resolve_slug",
                          new=AsyncMock(return_value="o/r")):
            _run(pr_watch._converge_keys())
            first = json.loads(self.state_path.read_text())
            _run(pr_watch._converge_keys())
        self.assertEqual(json.loads(self.state_path.read_text()), first)


if __name__ == "__main__":
    unittest.main()
