"""Tests for ship-check.

No mocking: a real git repository, real attestation tokens signed by `attest`
against that repository's real diff, and a real `gh` executable on disk that
serves a pull-request payload the test controls. The properties under test are
exactly the ones a string comparison would get wrong - a forged id, a stale
trailer, and a trailer that appears only in a comment.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
ATTEST_SRC = Path(__file__).resolve().parents[2] / "attest" / "src"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(ATTEST_SRC))

import attest  # noqa: E402
import ship_check  # noqa: E402

# A `gh` that answers `api repos/<slug>/pulls/<n>` from a JSON file the test
# writes, and records every invocation. Anything else exits non-zero, which is
# how the suite proves the check never reaches for a PR's comments.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write(json.dumps(argv) + "\n")
if argv[:1] == ["api"] and argv[1].startswith("repos/") and "/pulls/" in argv[1]:
    # Colourised, as the real gh is for a user with `color: always` - which is
    # how a perfectly good API response first came back as "non-JSON output".
    sys.stdout.write("\x1b[1;38m" + open(os.environ["FAKE_GH_PR"]).read() + "\x1b[m")
else:
    sys.stderr.write("unexpected: %r\n" % (argv,))
    sys.exit(9)
"""


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


class ShipCheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

        # A real repo with a real remote, so the binding check can fetch and diff.
        self.remote = tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)],
                       check=True, capture_output=True)
        self.repo = tmp / "repo"
        self.repo.mkdir()
        _git(tmp, "init", "-q", "-b", "main", str(self.repo))
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "README.md").write_text("start\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "initial")
        _git(self.repo, "push", "-q", "origin", "main")
        _git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "app.py").write_text("value = 1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "feature")
        _git(self.repo, "push", "-q", "origin", "feature")

        self.gh_log = tmp / "gh.log"
        self.pr_file = tmp / "pr.json"
        gh = tmp / "gh"
        gh.write_text(FAKE_GH)
        gh.chmod(0o755)

        self._saved = {key: os.environ.get(key) for key in
                       ("ATTEST_HOME", "SHIP_CHECK_HOME", "FAKE_GH_LOG", "FAKE_GH_PR",
                        "GH_BIN")}
        self.addCleanup(self._restore)
        os.environ["ATTEST_HOME"] = str(tmp / "state")
        os.environ["SHIP_CHECK_HOME"] = str(tmp / "state")
        os.environ["FAKE_GH_LOG"] = str(self.gh_log)
        os.environ["FAKE_GH_PR"] = str(self.pr_file)
        os.environ["GH_BIN"] = str(gh)
        self._saved_gh_bin = ship_check.GH_BIN
        ship_check.GH_BIN = str(gh)
        self.fake_gh = str(gh)

    def _restore(self):
        ship_check.GH_BIN = self._saved_gh_bin
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    # -- helpers ----------------------------------------------------------

    def head_sha(self, ref="feature"):
        return _git(self.repo, "rev-parse", ref).strip()

    def tokens(self, base="main", head="feature"):
        """Both required claims, signed against this repository's real diff."""
        import asyncio
        sha = asyncio.run(attest.diff_sha(str(self.repo), base, head))
        return [
            str(attest._issue("design_reviewed", sha, str(self.repo), base, head,
                              "ENG-1", "q" * 64, 1, {})),
            str(attest._issue("eval_passed", sha, str(self.repo), base, head,
                              None, None, 0, {})),
        ]

    def trailer(self, tokens):
        return "Shipped-With: jj_ship/0.2.0 attest=" + ",".join(
            attest.token_id(token) for token in tokens)

    def write_pr(self, body, base="main", head="feature", head_sha=None,
                 comments_body=None):
        payload = {
            "body": body,
            "base": {"ref": base},
            "head": {"ref": head, "sha": head_sha or self.head_sha(head)},
            "state": "open",
            "draft": False,
            "html_url": "https://github.com/o/r/pull/1",
        }
        if comments_body is not None:
            payload["_comments"] = [{"body": comments_body}]
        self.pr_file.write_text(json.dumps(payload))

    def gh_calls(self):
        if not self.gh_log.exists():
            return []
        return [json.loads(line) for line in
                self.gh_log.read_text().strip().split("\n") if line]

    def message(self, url="https://github.com/o/r/pull/1", name="worker-1"):
        return (f"[from child:{name}]\nAgent-to-agent message received.\n"
                f"Source: agent_message\n"
                f"From: active abc123def456, session 0199-aaa, client agent\n"
                f"To: orchestrator, active ffffff000000\n"
                f"Message id: agentmsg_1\n\nPR is up: {url} - please review.")

    # -- extraction -------------------------------------------------------

    def test_pr_urls_are_extracted_deduplicated_and_normalised(self):
        text = ("see https://github.com/o/r/pull/1 and "
                "http://www.github.com/o/r/pull/1, plus "
                "https://github.com/a/b/pull/22/files, not "
                "https://github.com/o/r/issues/3 nor https://example.com/x/y/pull/9")
        self.assertEqual([pr["url"] for pr in ship_check.find_pr_urls(text)],
                         ["https://github.com/o/r/pull/1",
                          "https://github.com/a/b/pull/22"])

    def test_the_last_trailer_wins_when_a_body_was_stamped_twice(self):
        body = "x\n\nShipped-With: jj_ship/0.1.0 attest=aaaaaaaaaaaa\n\ny\n\n" \
               "Shipped-With: jj_ship/0.2.0 attest=bbbbbbbbbbbb,cccccccccccc\n"
        self.assertEqual(ship_check.parse_trailer(body),
                         ["bbbbbbbbbbbb", "cccccccccccc"])

    def test_the_sender_is_identified_from_the_agent_message_header(self):
        sender = ship_check.find_sender(self.message())
        self.assertEqual(sender, {"role": "child", "name": "worker-1",
                                  "active_session_id": "abc123def456"})

    # -- what passes ------------------------------------------------------

    def test_a_trailer_bound_to_the_prs_diff_passes(self):
        tokens = self.tokens()
        self.write_pr("Body.\n\n" + self.trailer(tokens) + "\n")
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertTrue(verdict["ok"], verdict["reason"])
        self.assertEqual(verdict["claims"], ["design_reviewed", "eval_passed"])

    # -- what fails -------------------------------------------------------

    def test_a_body_without_a_trailer_fails(self):
        self.write_pr("Body with no trailer.\n")
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("no `Shipped-With:` trailer", verdict["reason"])

    def test_a_trailer_that_exists_only_in_a_comment_fails(self):
        """Emeka kept the literal prefix out of a PR comment for this reason: a
        check that swept comments would pass a PR no tool ever stamped."""
        tokens = self.tokens()
        self.write_pr("Body with no trailer.\n",
                      comments_body="for reference the format is "
                                    + self.trailer(tokens))
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("no `Shipped-With:` trailer", verdict["reason"])
        self.assertEqual([call for call in self.gh_calls()
                          if any("comment" in part for part in call)], [])

    def test_a_forged_trailer_fails_even_though_it_matches_the_format(self):
        self.write_pr("Body.\n\nShipped-With: jj_ship/0.2.0 "
                      "attest=deadbeefcafe,0123456789ab\n")
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("no issuance record", verdict["reason"])
        self.assertIn("deadbeefcafe", verdict["reason"])

    def test_one_claim_short_fails_and_names_the_missing_claim(self):
        tokens = self.tokens()
        self.write_pr("Body.\n\n" + self.trailer(tokens[1:]) + "\n")
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("design_reviewed", verdict["reason"])

    def test_a_stale_trailer_fails_after_another_commit_is_pushed(self):
        tokens = self.tokens()
        body = "Body.\n\n" + self.trailer(tokens) + "\n"
        (self.repo / "app.py").write_text("value = 2\n")
        _git(self.repo, "commit", "-aqm", "one more edit")
        _git(self.repo, "push", "-q", "origin", "feature")
        self.write_pr(body, head_sha=self.head_sha())
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("bound to a different diff", verdict["reason"])

    def test_a_trailer_issued_for_another_branch_fails(self):
        tokens = self.tokens(head="feature")
        self.write_pr("Body.\n\n" + self.trailer(tokens) + "\n", head="other-branch",
                      head_sha=self.head_sha("feature"))
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertFalse(verdict["ok"])
        self.assertIn("head branch", verdict["reason"])


    def test_a_base_recorded_as_a_merge_base_sha_still_passes(self):
        """Passing the merge-base sha is the recommended way to attest, so a
        record whose `base` is a sha must not be rejected for not being a name.
        This failed for real on jack-michaud/nix#20, the PR that added it."""
        import asyncio
        base_sha = _git(self.repo, "rev-parse", "main").strip()
        diff_sha = asyncio.run(attest.diff_sha(str(self.repo), base_sha, "feature"))
        tokens = [
            str(attest._issue("design_reviewed", diff_sha, str(self.repo), base_sha,
                              "feature", "ENG-1", "q" * 64, 1, {})),
            str(attest._issue("eval_passed", diff_sha, str(self.repo), base_sha,
                              "feature", None, None, 0, {})),
        ]
        self.write_pr("Body.\n\n" + self.trailer(tokens) + "\n")
        verdict = ship_check.verify_pr("o/r", 1)
        self.assertTrue(verdict["ok"], verdict["reason"])

    # -- the once-per-PR policy ------------------------------------------

    def test_a_pr_url_is_checked_once_and_the_record_survives_a_new_process(self):
        self.write_pr("Body with no trailer.\n")
        first = ship_check.check_message(self.message())
        self.assertEqual([verdict["url"] for verdict in first["verdicts"]],
                         ["https://github.com/o/r/pull/1"])
        self.assertEqual(first["skipped"], [])
        calls_after_first = len(self.gh_calls())

        second = ship_check.check_message(self.message())
        self.assertEqual(second["verdicts"], [])
        self.assertEqual(second["skipped"], ["https://github.com/o/r/pull/1"])
        self.assertEqual(len(self.gh_calls()), calls_after_first)
        self.assertEqual(second["notice"], "")

        # A separate process reads the same record: the dedupe is on disk.
        proc = subprocess.run([sys.executable, "-m", "ship_check", "--message-stdin"],
                              input=self.message(), capture_output=True, text=True,
                              env={**os.environ,
                                   "PYTHONPATH": os.pathsep.join([str(SRC), str(ATTEST_SRC)])})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["skipped"],
                         ["https://github.com/o/r/pull/1"])
        self.assertEqual(len(self.gh_calls()), calls_after_first)

    def test_the_notice_names_the_failure_and_the_exact_remediation(self):
        self.write_pr("Body with no trailer.\n")
        result = ship_check.check_message(self.message(name="ret-999-worker"))
        notice = result["notice"]
        self.assertIn(ship_check.NOTICE_HEADER, notice)
        self.assertIn("https://github.com/o/r/pull/1", notice)
        self.assertIn("jj_ship", notice)
        self.assertIn('receiver_role="child", receiver_name="ret-999-worker"', notice)

    def test_a_passing_pr_produces_no_notice(self):
        tokens = self.tokens()
        self.write_pr("Body.\n\n" + self.trailer(tokens) + "\n")
        result = ship_check.check_message(self.message())
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["notice"], "")


if __name__ == "__main__":
    unittest.main()
