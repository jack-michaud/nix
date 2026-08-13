"""Unit tests for jj_ship's markdown hard-wrap detection/normalization and its
enforcement in open_pr()/ship() (added after real PRs - fayhealthinc/fay-ui
#3732, #3743, #3745, fayhealthinc/fay-service#7207 - were opened with bodies
GitHub rendered as visibly broken paragraphs, because GFM treats a single
"\n" inside a paragraph as a hard line break, not a soft one).

Runs with plain `python3 -m unittest` - no pytest dependency, no `gh`/`jj`
binary required (the `_gh`/`_jj` calls are monkeypatched where needed).
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import jj_ship  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# Real (excerpted) hard-wrapped bodies from this session's bad PRs.
BAD_3745_A = (
    "The progress tab announcement modal was supposed to trigger when a "
    "provider navigates\n"
    "(client-side, SPA navigation) to a client-details screen, but it only\n"
    "triggered on a hard page refresh."
)
BAD_3745_B = (
    "`PromptQueueContext`'s prompt state machine was strictly forward-only\n"
    "(`loading -> active -> released`, never backward). `Announcements`/"
    "`useAnnouncements`\n"
    "release the \"announcements\" queue slot whenever no announcement is "
    "currently eligible\n"
    "for the page (e.g. a page-gated announcement not eligible on the page "
    "a provider\n"
    "first lands on). Since `PromptQueueProvider`/`Announcements` are "
    "mounted once near the\n"
    "app root and never remount on navigation, once that slot hit "
    "\"released...\""
)
BAD_7207_A = (
    "Intercom identity tokens are hardcoded to a 1-hour lifetime, and QA "
    "has no way to\n"
    "exercise expired-token behavior (e.g. investigating an iOS token "
    "refresh bug) without\n"
    "waiting an hour. This adds a self-service Statsig lever so specific "
    "patients can be\n"
    "given a much shorter token lifetime."
)
BAD_7207_B = (
    "This PR is backend-only, per the ticket's suggested phasing. "
    "`fay-ui`'s\n"
    "client-side refresh interval is a separate, deliberately deferred "
    "piece of work (see\n"
    "Tricky bits below)."
)

CLEAN_BODY = """**Fixes the widget so it renders correctly.**

## Context

The widget broke after the last refactor. Some background here that ends with a colon:

- item one
- item two
- item three

```python
def foo():
    return 1
```

A table:

| a | b |
|---|---|
| 1 | 2 |

> A blockquote
> spanning several lines is real structure.

## Evidence

Ran the tests, they passed.
"""


class FindHardWrappedLinesTest(unittest.TestCase):
    def test_flags_each_real_bad_excerpt(self):
        for name, body, expected_min_hits in [
            ("3745a", BAD_3745_A, 2),
            ("3745b", BAD_3745_B, 4),
            ("7207a", BAD_7207_A, 2),
            ("7207b", BAD_7207_B, 1),
        ]:
            with self.subTest(name):
                hits = jj_ship.find_hard_wrapped_lines(body)
                self.assertGreaterEqual(len(hits), expected_min_hits, hits)

    def test_clean_body_produces_zero_hits(self):
        self.assertEqual(jj_ship.find_hard_wrapped_lines(CLEAN_BODY), [])

    def test_code_fence_lines_are_never_flagged(self):
        body = "prose\n\n```\nshort\nlines\nno punctuation\n```\n\nmore prose."
        hits = jj_ship.find_hard_wrapped_lines(body)
        self.assertEqual(hits, [])

    def test_list_items_are_never_flagged(self):
        body = "- first item\n- second item\n- third item"
        self.assertEqual(jj_ship.find_hard_wrapped_lines(body), [])

    def test_headers_and_table_rows_are_never_flagged(self):
        body = "# Heading\nSome text.\n\n| a | b |\n|---|---|\n| 1 | 2 |"
        self.assertEqual(jj_ship.find_hard_wrapped_lines(body), [])

    def test_blockquote_lines_are_never_flagged(self):
        body = "> line one\n> line two"
        self.assertEqual(jj_ship.find_hard_wrapped_lines(body), [])


class NormalizeMarkdownBodyTest(unittest.TestCase):
    def test_fixes_known_bad_bodies_to_zero_hits(self):
        for body in (BAD_3745_A, BAD_3745_B, BAD_7207_A, BAD_7207_B):
            fixed = jj_ship.normalize_markdown_body(body)
            self.assertEqual(jj_ship.find_hard_wrapped_lines(fixed), [])

    def test_leaves_clean_body_byte_for_byte_unchanged(self):
        self.assertEqual(jj_ship.normalize_markdown_body(CLEAN_BODY), CLEAN_BODY)

    def test_joins_with_a_single_space_not_concatenation(self):
        fixed = jj_ship.normalize_markdown_body(BAD_7207_B)
        self.assertNotIn("ui`'s\nclient", fixed)
        self.assertIn("ui`'s client", fixed)


class OpenPrWrapEnforcementTest(unittest.TestCase):
    """open_pr() must reject a hard-wrapped body without ever calling gh."""

    def test_raises_without_calling_gh(self):
        gh_mock = AsyncMock()
        with patch.object(jj_ship, "_gh", new=gh_mock), \
             patch.object(jj_ship, "current_bookmark", new=AsyncMock(return_value="my-branch")), \
             patch.object(jj_ship, "_default_branch", new=AsyncMock(return_value="main")):
            with self.assertRaises(jj_ship.JjShipError) as ctx:
                _run(jj_ship.open_pr("Title", body=BAD_7207_B, repo="."))
        gh_mock.assert_not_called()
        self.assertIn("normalize_markdown_body", str(ctx.exception))

    def test_skip_wrap_check_bypasses_the_raise(self):
        async def _fake_gh(args, repo, check=True):
            if args[:2] == ["pr", "list"]:
                return {"argv": args, "code": 0, "out": "[]", "err": ""}
            if args[:2] == ["pr", "create"]:
                return {"argv": args, "code": 0,
                        "out": "https://github.com/o/r/pull/1", "err": ""}
            raise AssertionError(f"unexpected gh call: {args}")

        with patch.object(jj_ship, "_gh", new=AsyncMock(side_effect=_fake_gh)), \
             patch.object(jj_ship, "current_bookmark", new=AsyncMock(return_value="my-branch")), \
             patch.object(jj_ship, "_default_branch", new=AsyncMock(return_value="main")):
            # draft=True because this test is about the wrap check, which runs
            # before (and independently of) the attestation gate.
            result = _run(jj_ship.open_pr(
                "Title", body=BAD_7207_B, repo=".", skip_wrap_check=True,
                draft=True))
        self.assertTrue(result["created"])

    def test_clean_body_passes_straight_through(self):
        async def _fake_gh(args, repo, check=True):
            if args[:2] == ["pr", "list"]:
                return {"argv": args, "code": 0, "out": "[]", "err": ""}
            if args[:2] == ["pr", "create"]:
                return {"argv": args, "code": 0,
                        "out": "https://github.com/o/r/pull/2", "err": ""}
            raise AssertionError(f"unexpected gh call: {args}")

        with patch.object(jj_ship, "_gh", new=AsyncMock(side_effect=_fake_gh)), \
             patch.object(jj_ship, "current_bookmark", new=AsyncMock(return_value="my-branch")), \
             patch.object(jj_ship, "_default_branch", new=AsyncMock(return_value="main")):
            result = _run(jj_ship.open_pr("Title", body=CLEAN_BODY, repo=".",
                                          draft=True))
        self.assertTrue(result["created"])


class ShipInheritsWrapEnforcementTest(unittest.TestCase):
    """ship() calls open_pr() internally, so the same check must fire."""

    def test_ship_raises_on_hard_wrapped_body_without_calling_gh(self):
        gh_mock = AsyncMock()
        jj_mock = AsyncMock(return_value={"argv": [], "code": 0, "out": "", "err": ""})
        with patch.object(jj_ship, "_gh", new=gh_mock), \
             patch.object(jj_ship, "_jj", new=jj_mock), \
             patch.object(jj_ship, "status", new=AsyncMock(return_value={
                 "change": "x", "description": "", "empty": False,
                 "bookmarks": ["my-branch"], "parent_bookmarks": [], "status": "",
             })), \
             patch.object(jj_ship, "_default_branch", new=AsyncMock(return_value="main")):
            with self.assertRaises(jj_ship.JjShipError):
                _run(jj_ship.ship("msg", bookmark="my-branch", body=BAD_3745_A, repo="."))
        gh_mock.assert_not_called()


class RepoSlugResolutionTest(unittest.TestCase):
    """`gh` infers its repo from cwd's git remote, and a `jj workspace add`
    directory has no `.git` - so every _gh-backed entry point (checks, find_pr,
    comments, _default_branch, and therefore open_pr/ship/watch) died with
    "failed to run git: fatal: not a git repository". Confirmed live from a real
    workspace. These cases pin the resolution order, which is duplicated in the
    pr-watch skill's pr_watch._resolve_slug and must not drift from it."""

    def setUp(self):
        jj_ship._SLUG_CACHE.clear()

    def tearDown(self):
        jj_ship._SLUG_CACHE.clear()

    def test_falls_back_to_jj_origin_when_there_is_no_git_dir(self):
        async def _fake_exec(argv, cwd=".", check=True, timeout=600, env=None):
            if argv[0] == "git":
                return {"argv": argv, "code": 128, "out": "",
                        "err": ("fatal: not a git repository (or any of the "
                                "parent directories): .git")}
            # Real `jj git remote list` output from fay-service: the GitHub
            # `origin` is neither first nor the only remote.
            return {"argv": argv, "code": 0, "err": "", "out": (
                "bitbucket git@bitbucket.org:fayhealthinc/fay-service.git\n"
                "no-mistakes /Users/j/.no-mistakes/repos/0b7165a5.git\n"
                "origin git@github.com:fayhealthinc/fay-service.git")}

        with patch.object(jj_ship, "_exec", new=AsyncMock(side_effect=_fake_exec)):
            jj_ship.os.environ.pop("GH_REPO", None)
            slug = _run(jj_ship._resolve_slug("."))
        # NOT the bitbucket remote, which is what "take the first line" gives.
        self.assertEqual(slug, "fayhealthinc/fay-service")

    def test_resolution_is_cached_per_path(self):
        calls = []

        async def _fake_exec(argv, cwd=".", check=True, timeout=600, env=None):
            calls.append(argv[0])
            return {"argv": argv, "code": 0, "out": "https://github.com/o/r.git",
                    "err": ""}

        with patch.object(jj_ship, "_exec", new=AsyncMock(side_effect=_fake_exec)):
            path = str(Path(".").resolve())
            self.assertEqual(_run(jj_ship._resolve_slug(path)), "o/r")
            self.assertEqual(_run(jj_ship._resolve_slug(path)), "o/r")
        # watch() polls up to 40 times; resolution must not reshell each poll.
        self.assertEqual(len(calls), 1)

    def test_unresolvable_repo_fails_loudly(self):
        async def _fake_exec(argv, cwd=".", check=True, timeout=600, env=None):
            return {"argv": argv, "code": 128, "out": "",
                    "err": "not a repo of any kind"}

        with patch.object(jj_ship, "_exec", new=AsyncMock(side_effect=_fake_exec)):
            jj_ship.os.environ.pop("GH_REPO", None)
            with self.assertRaises(jj_ship.JjShipError) as ctx:
                _run(jj_ship._resolve_slug("."))
        self.assertIn("cannot determine the GitHub repo", str(ctx.exception))

    def test_non_github_origin_is_rejected(self):
        self.assertIsNone(
            jj_ship._parse_github_url("git@bitbucket.org:fayhealthinc/fay-service.git"))
        self.assertEqual(jj_ship._parse_github_url("git@github.com:o/r.git"), "o/r")
        self.assertEqual(jj_ship._parse_github_url("https://github.com/o/r"), "o/r")
        self.assertEqual(jj_ship._parse_github_url("ssh://git@github.com/o/r.git"), "o/r")


class GhGetsTheRepoInItsEnvTest(unittest.TestCase):
    """The actual fix: _gh must pass GH_REPO, and must do so for `gh api
    graphql` too - which is why this is an env var and not a `--repo` flag
    (graphql rejects --repo, so a blanket flag would break comments())."""

    def setUp(self):
        jj_ship._SLUG_CACHE.clear()

    def tearDown(self):
        jj_ship._SLUG_CACHE.clear()

    def test_gh_is_given_gh_repo_in_its_env(self):
        seen = {}

        async def _fake_exec(argv, cwd=".", check=True, timeout=600, env=None):
            seen["argv"] = argv
            seen["env"] = env
            return {"argv": argv, "code": 0, "out": "", "err": ""}

        with patch.object(jj_ship, "_exec", new=AsyncMock(side_effect=_fake_exec)), \
                patch.object(jj_ship, "_resolve_slug",
                             new=AsyncMock(return_value="o/r")):
            _run(jj_ship._gh(["api", "graphql", "-f", "query=x"], repo="."))
        self.assertEqual(seen["env"], {"GH_REPO": "o/r"})
        # No --repo flag was added: `gh api graphql` would reject it.
        self.assertNotIn("--repo", seen["argv"])


class BookmarkNameHasNoSyncMarkerTest(unittest.TestCase):
    """jj renders a bookmark that differs from its remote as "name*", and that
    string was fed straight to `jj git push --bookmark`, which rejected it with
    "No such bookmark: name*". So the FIRST push to a new bookmark worked and the
    second one - the re-push that updates an open PR - failed. Hit live."""

    def test_status_asks_jj_for_bare_bookmark_names(self):
        seen = []

        async def _fake_jj(args, repo=".", **kw):
            seen.append(args)
            return {"argv": args, "code": 0, "out": "", "err": ""}

        with patch.object(jj_ship, "_jj", new=AsyncMock(side_effect=_fake_jj)):
            _run(jj_ship.status(repo="."))
        templates = [a[a.index("-T") + 1] for a in seen if "-T" in a]
        bookmark_templates = [t for t in templates if "bookmarks" in t]
        self.assertTrue(bookmark_templates, "status() asked jj for no bookmarks")
        for t in bookmark_templates:
            # `.name()` is what strips the `*`; a bare `bookmarks.join(...)`
            # reintroduces the bug.
            self.assertIn("name()", t)

    def test_current_bookmark_is_pushable_verbatim(self):
        async def _fake_status(repo="."):
            return {"change": "x", "description": "", "empty": False,
                    "bookmarks": ["my-branch"], "parent_bookmarks": [], "status": ""}

        with patch.object(jj_ship, "status", new=AsyncMock(side_effect=_fake_status)):
            self.assertEqual(_run(jj_ship.current_bookmark(repo=".")), "my-branch")


# ---------------------------------------------------------------------------
# attestation enforcement
# ---------------------------------------------------------------------------
# These tests use a real git repository and a real fake `gh` on PATH (via
# GH_BIN) rather than patching jj_ship's internals. Two reasons: the whole
# attestation path is about what actually reaches `gh pr create`, which a
# patched `_gh` cannot show; and attest.eval_passed() - the gate these very
# changes install - counts `mock.patch(`/`MagicMock` as violations, so a suite
# that cannot be written without them could never ship through its own gate.

ATTEST_SRC = Path(__file__).resolve().parents[2] / "attest" / "src"
sys.path.insert(0, str(ATTEST_SRC))

import attest  # noqa: E402

# A `gh` that records every invocation and answers the handful of subcommands
# the shipping path uses. Written to disk and pointed at with GH_BIN.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(argv) + "\n")
if argv[:2] == ["repo", "view"]:
    print("main")
elif argv[:2] == ["pr", "list"]:
    print("[]")
elif argv[:2] == ["pr", "create"]:
    print("https://github.com/o/r/pull/1")
elif argv[:2] == ["pr", "view"]:
    print(json.dumps({"number": 1, "url": "https://github.com/o/r/pull/1",
                      "body": "**Original body.**", "headRefName": "feature",
                      "baseRefName": "main", "isDraft": True}))
elif argv[:2] in (["pr", "edit"], ["pr", "ready"]):
    pass
else:
    sys.stderr.write("unexpected: %r\n" % (argv,))
    sys.exit(9)
"""


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


class AttestationEnforcementTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        self.repo = tmp / "repo"
        self.repo.mkdir()
        _git(tmp, "init", "-q", "-b", "main", str(self.repo))
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "remote", "add", "origin", "git@github.com:o/r.git")
        (self.repo / "README.md").write_text("start\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "initial")
        _git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "app.py").write_text("value = 1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "feature")

        gh = tmp / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)
        self.gh_log = tmp / "gh.log"

        self._saved = {k: os.environ.get(k) for k in
                       ("ATTEST_HOME", "FAKE_GH_LOG", "GH_REPO")}
        self.addCleanup(self._restore)
        os.environ["ATTEST_HOME"] = str(tmp / "state")
        os.environ["FAKE_GH_LOG"] = str(self.gh_log)
        os.environ.pop("GH_REPO", None)
        self._saved_gh_bin = jj_ship.GH_BIN
        jj_ship.GH_BIN = str(gh)
        jj_ship._SLUG_CACHE.clear()

    def _restore(self):
        jj_ship.GH_BIN = self._saved_gh_bin
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def gh_calls(self):
        if not self.gh_log.exists():
            return []
        return [json.loads(line) for line in
                self.gh_log.read_text().strip().split("\n") if line]

    def created_body(self):
        for argv in self.gh_calls():
            if argv[:2] == ["pr", "create"]:
                return argv[argv.index("--body") + 1]
        raise AssertionError(f"no `pr create` in {self.gh_calls()!r}")

    def tokens(self):
        """Both required claims, signed against the current diff.

        Signed directly rather than through design_reviewed(): that function's
        Linear fetch and quote/path matching are covered by the attest suite,
        while what jj-ship owns is refusing a PR whose tokens do not match.
        """
        sha = _run(attest.diff_sha(str(self.repo), "main", "feature"))
        return [
            str(attest._issue("design_reviewed", sha, str(self.repo), "main",
                              "feature", "ENG-1", "q" * 64, 1, {})),
            str(_run(attest.eval_passed(str(self.repo), "main", "feature"))),
        ]

    # -- refusals ---------------------------------------------------------

    def test_a_non_draft_pr_without_attestations_names_every_missing_claim(self):
        with self.assertRaises(jj_ship.JjShipError) as ctx:
            _run(jj_ship.open_pr("T", body="**Body.**", repo=str(self.repo),
                                 head="feature"))
        message = str(ctx.exception)
        self.assertIn("missing attestation(s)", message)
        self.assertIn("design_reviewed", message)
        self.assertIn("eval_passed", message)
        self.assertNotIn(["pr", "create"], [c[:2] for c in self.gh_calls()])

    def test_one_claim_short_names_only_the_missing_one(self):
        both = self.tokens()
        with self.assertRaises(jj_ship.JjShipError) as ctx:
            _run(jj_ship.open_pr("T", body="**Body.**", repo=str(self.repo),
                                 head="feature", attestations=[both[1]]))
        self.assertIn("design_reviewed", str(ctx.exception))

    def test_an_edit_after_attestation_voids_the_token(self):
        tokens = self.tokens()
        (self.repo / "app.py").write_text("value = 2\n")
        _git(self.repo, "commit", "-aqm", "one more edit")
        with self.assertRaises(jj_ship.JjShipError) as ctx:
            _run(jj_ship.open_pr("T", body="**Body.**", repo=str(self.repo),
                                 head="feature", attestations=tokens))
        message = str(ctx.exception)
        self.assertIn("attestation is bound to a different diff - re-run the "
                      "verification after your last edit", message)
        self.assertNotIn(["pr", "create"], [c[:2] for c in self.gh_calls()])

    # -- what is allowed --------------------------------------------------

    def test_a_draft_needs_no_attestation(self):
        result = _run(jj_ship.open_pr("T", body="**Body.**", repo=str(self.repo),
                                      head="feature", draft=True))
        self.assertTrue(result["created"])
        create = next(c for c in self.gh_calls() if c[:2] == ["pr", "create"])
        self.assertIn("--draft", create)
        # ...and stays clean of a trailer naming tokens that do not exist.
        self.assertNotIn("Shipped-With:", self.created_body())

    def test_valid_attestations_open_the_pr_and_stamp_the_trailer(self):
        tokens = self.tokens()
        result = _run(jj_ship.open_pr("T", body="**Body.**", repo=str(self.repo),
                                      head="feature", attestations=tokens))
        self.assertTrue(result["created"])
        body = self.created_body()
        expected = jj_ship.attestation_trailer([attest.token_id(t) for t in tokens])
        self.assertIn(expected, body)
        self.assertIn(f"jj_ship/{jj_ship.VERSION}", body)
        # The trailer carries IDs, never the bearer tokens themselves.
        for token in tokens:
            self.assertNotIn(token, body)

    def test_mark_ready_refuses_without_attestations_and_accepts_with_them(self):
        tokens = self.tokens()
        with self.assertRaises(jj_ship.JjShipError) as ctx:
            _run(jj_ship.mark_ready(1, repo=str(self.repo)))
        self.assertIn("missing attestation(s)", str(ctx.exception))
        self.assertNotIn(["pr", "ready"], [c[:2] for c in self.gh_calls()])

        result = _run(jj_ship.mark_ready(1, repo=str(self.repo), attestations=tokens))
        self.assertTrue(result["ready"])
        self.assertIn(["pr", "ready"], [c[:2] for c in self.gh_calls()])
        edit = next(c for c in self.gh_calls() if c[:2] == ["pr", "edit"])
        edited_body = edit[edit.index("--body") + 1]
        self.assertIn("**Original body.**", edited_body)
        self.assertIn("Shipped-With:", edited_body)

    def test_ship_keeps_its_old_signature_and_takes_attestations_by_keyword(self):
        signature = inspect.signature(jj_ship.ship)
        parameter = signature.parameters["attestations"]
        self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameter.default)
        positional = [name for name, p in signature.parameters.items()
                      if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD]
        self.assertEqual(positional[:4], ["message", "bookmark", "title", "body"])


if __name__ == "__main__":
    unittest.main()
