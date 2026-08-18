"""Unit tests for the attest skill.

Runs with plain `python3 -m unittest` - no pytest, no network, no Linear
account. Every fixture is real rather than patched: git repositories are
created in a temp directory and really committed to, and the Linear fetch is
pointed at a small in-process HTTP server serving a GraphQL-shaped response
(ATTEST_LINEAR_ENDPOINT). That is deliberate - the skill's own eval_passed()
rejects `mock.patch(`/`MagicMock`/`monkeypatch.setattr` in a diff, so its test
suite has to be able to pass its own gate.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import attest  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout


def make_repo(root: Path, files: dict[str, str]) -> Path:
    """A real git repo with `main` at an initial commit and a `feature` branch
    holding `files`. Returns the repo path."""
    repo = root / "repo"
    repo.mkdir()
    _git(repo.parent, "init", "-q", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("start\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "initial")
    _git(repo, "checkout", "-q", "-b", "feature")
    write_files(repo, files)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "feature")
    return repo


def write_files(repo: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class _StubLinear(BaseHTTPRequestHandler):
    """A real HTTP server speaking just enough Linear GraphQL.

    `description` is read off the class so a test can choose the document body
    without patching anything.
    """

    description = ""
    comments: list[str] = []

    def do_POST(self):  # noqa: N802 - BaseHTTPRequestHandler's naming
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length) or b"{}")
        doc_id = (request.get("variables") or {}).get("id", "ENG-1")
        body = json.dumps({"data": {"issue": {
            "id": "uuid", "identifier": doc_id, "title": "Design",
            "url": f"https://linear.app/x/issue/{doc_id}",
            "description": type(self).description,
            "comments": {"nodes": [{"body": c} for c in type(self).comments]},
        }}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class AttestTestCase(unittest.TestCase):
    """Base: an isolated ATTEST_HOME and a temp dir, restored afterwards."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        # .resolve() because macOS's temp dir is a symlink (/var -> /private/var)
        # and attest resolves the paths it reports.
        self.tmp = Path(self._tmp.name).resolve()
        self._saved_env = {k: os.environ.get(k) for k in
                           ("ATTEST_HOME", "ATTEST_LINEAR_ENDPOINT", "LINEAR_API_KEY")}
        os.environ["ATTEST_HOME"] = str(self.tmp / "state")
        os.environ["LINEAR_API_KEY"] = "lin_api_test"
        os.environ.pop("ATTEST_LINEAR_ENDPOINT", None)

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def serve_design(self, description: str, comments: list[str] | None = None) -> None:
        _StubLinear.description = description
        _StubLinear.comments = comments or []
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StubLinear)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        os.environ["ATTEST_LINEAR_ENDPOINT"] = \
            f"http://127.0.0.1:{server.server_address[1]}/graphql"


CLEAN_FILES = {
    "src/app.py": "\n".join(f"value_{i} = {i}" for i in range(60)) + "\n",
    "tests/test_app.py": "def test_app():\n    assert True\n",
}


class TokenRoundTripTest(AttestTestCase):
    def test_token_round_trips_and_the_key_is_0600(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.eval_passed(str(repo), "main", "feature"))
        payload = attest.decode(token)
        self.assertEqual(payload["claim"], "eval_passed")
        self.assertEqual(payload["diff_sha"],
                         _run(attest.diff_sha(str(repo), "main", "feature")))
        self.assertEqual(payload["base"], "main")
        self.assertEqual(payload["head"], "feature")
        self.assertEqual(oct(attest.key_path().stat().st_mode & 0o777), "0o600")

    def test_every_issued_token_is_appended_to_the_log(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        first = _run(attest.eval_passed(str(repo), "main", "feature"))
        second = _run(attest.eval_passed(str(repo), "main", "feature"))
        lines = attest.log_path().read_text().strip().split("\n")
        self.assertEqual(len(lines), 2)
        logged = [json.loads(line)["token_id"] for line in lines]
        self.assertEqual(logged, [attest.token_id(first), attest.token_id(second)])

    def test_a_tampered_payload_fails_the_hmac(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = str(_run(attest.eval_passed(str(repo), "main", "feature")))
        payload_b64, _, signature = token.partition(".")
        forged = attest._b64(json.dumps(
            {**json.loads(attest._unb64(payload_b64)), "diff_sha": "0" * 64},
            sort_keys=True, separators=(",", ":")).encode())
        with self.assertRaises(attest.AttestError) as ctx:
            attest.decode(f"{forged}.{signature}")
        self.assertIn("signature does not verify", str(ctx.exception))

    def test_a_malformed_token_is_rejected_not_crashed_on(self):
        with self.assertRaises(attest.AttestError) as ctx:
            attest.decode("not-a-token")
        self.assertIn("malformed attestation", str(ctx.exception))


class BindingToTheDiffTest(AttestTestCase):
    """The case that matters: attest, then edit, and the token is void."""

    def test_an_edit_after_attestation_voids_the_token(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.eval_passed(str(repo), "main", "feature"))
        attested_sha = attest.decode(token)["diff_sha"]
        # Holds before the edit. Only the eval_passed claim is required here -
        # the binding, not the required set, is what this test is about.
        attest.verify([token], attested_sha, required=("eval_passed",))

        write_files(repo, {"src/app.py": "value_0 = 0\nvalue_1 = 999\n"})
        _git(repo, "commit", "-aqm", "one more edit")
        new_sha = _run(attest.diff_sha(str(repo), "main", "feature"))
        self.assertNotEqual(new_sha, attested_sha)

        with self.assertRaises(attest.AttestError) as ctx:
            attest.verify([token], new_sha, required=("eval_passed",))
        message = str(ctx.exception)
        self.assertIn("attestation is bound to a different diff - re-run the "
                      "verification after your last edit", message)
        self.assertIn(attested_sha, message)
        self.assertIn(new_sha, message)

    def test_a_missing_claim_names_itself(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.eval_passed(str(repo), "main", "feature"))
        sha = attest.decode(token)["diff_sha"]
        with self.assertRaises(attest.AttestError) as ctx:
            attest.verify([token], sha)
        self.assertIn("design_reviewed", str(ctx.exception))
        self.assertNotIn("eval_passed", str(ctx.exception))

    def test_diff_sha_is_stable_across_repeated_calls(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        a = _run(attest.diff_sha(str(repo), "main", "feature"))
        b = _run(attest.diff_sha(str(repo), "main", "feature"))
        self.assertEqual(a, b)


DESIGN = """The queue must release its slot when no announcement is eligible.

Otherwise a provider who lands on an ineligible page never sees one again.
"""


class GitDirResolutionTest(AttestTestCase):
    """A `jj workspace add` directory has no `.git`, which is where a naive
    `git -C <dir>` dies. Hit live from a real workspace while shipping this
    skill, so it is pinned here."""

    def test_a_plain_checkout_resolves_to_its_own_git_dir(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        self.assertEqual(_run(attest._git_dir(str(repo))), str(repo / ".git"))

    def test_a_jj_workspace_follows_repo_then_git_target(self):
        repo = make_repo(self.tmp, CLEAN_FILES)
        workspace = self.tmp / "workspace"
        (workspace / ".jj").mkdir(parents=True)
        # The same two-hop pointer chain jj writes, with jj's relative paths.
        (workspace / ".jj" / "repo").write_text(str(repo / ".jj" / "repo"))
        (repo / ".jj" / "repo" / "store").mkdir(parents=True)
        (repo / ".jj" / "repo" / "store" / "git_target").write_text("../../../.git")
        self.assertEqual(_run(attest._git_dir(str(workspace))), str(repo / ".git"))
        # ...and the diff really is computable from the workspace path.
        self.assertEqual(_run(attest.diff_sha(str(workspace), "main", "feature")),
                         _run(attest.diff_sha(str(repo), "main", "feature")))

    def test_a_directory_that_is_neither_says_so(self):
        plain = self.tmp / "plain"
        plain.mkdir()
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest._git_dir(str(plain)))
        self.assertIn("no colocated git store", str(ctx.exception))


class DesignReviewedTest(AttestTestCase):
    def test_a_matching_quote_and_citation_yields_a_token(self):
        self.serve_design(DESIGN)
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.design_reviewed(
            repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
            # Re-wrapped on purpose: the match is modulo whitespace.
            quote="The queue must release its slot\n   when no announcement\nis eligible.",
            requirements=[("release the slot", "src/app.py:3")]))
        payload = attest.decode(token)
        self.assertEqual(payload["claim"], "design_reviewed")
        self.assertEqual(payload["doc_id"], "ENG-7")
        self.assertEqual(payload["requirements_n"], 1)
        self.assertEqual(token.report["doc"]["id"], "ENG-7")

    def test_a_quote_in_a_comment_counts_as_part_of_the_design(self):
        self.serve_design("A short body.", comments=["We decided to cap depth at three."])
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.design_reviewed(
            repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
            quote="We decided to cap depth at three.",
            requirements=[("cap depth", "src/app.py:1")]))
        self.assertEqual(attest.decode(token)["claim"], "design_reviewed")

    def test_a_quote_absent_from_the_fetched_design_raises(self):
        self.serve_design(DESIGN)
        repo = make_repo(self.tmp, CLEAN_FILES)
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.design_reviewed(
                repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
                quote="The design says nothing of the kind.",
                requirements=[("x", "src/app.py:1")]))
        self.assertIn("quote does not appear", str(ctx.exception))

    def test_a_requirement_path_not_in_the_diff_raises(self):
        self.serve_design(DESIGN)
        repo = make_repo(self.tmp, CLEAN_FILES)
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.design_reviewed(
                repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
                quote="The queue must release its slot when no announcement is eligible.",
                requirements=[("release the slot", "src/never_touched.py:12")]))
        message = str(ctx.exception)
        self.assertIn("src/never_touched.py", message)
        self.assertIn("src/app.py", message)  # says what the diff DOES touch

    def test_empty_requirements_or_quote_raise(self):
        self.serve_design(DESIGN)
        repo = make_repo(self.tmp, CLEAN_FILES)
        with self.assertRaises(attest.AttestError):
            _run(attest.design_reviewed(
                repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
                quote="The queue must release its slot when no announcement is eligible.",
                requirements=[]))
        with self.assertRaises(attest.AttestError):
            _run(attest.design_reviewed(
                repo=str(repo), base="main", head="feature", design_doc_id="ENG-7",
                quote="   ", requirements=[("x", "src/app.py:1")]))


class EvalReportTest(AttestTestCase):
    def test_a_comment_heavy_production_file_fails(self):
        files = {"src/app.py": "".join(
            [f"# explaining line {i}\nvalue_{i} = {i}\n" for i in range(20)])}
        repo = make_repo(self.tmp, files)
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.eval_passed(str(repo), "main", "feature"))
        self.assertIn("comment ratio", str(ctx.exception))

    def test_comments_in_test_files_are_not_counted(self):
        files = {"src/app.py": "\n".join(f"v{i} = {i}" for i in range(60)) + "\n",
                 "tests/test_app.py": "".join(
                     f"# a comment {i}\n" for i in range(40))}
        repo = make_repo(self.tmp, files)
        report = attest.eval_report(_run(attest.diff_text(str(repo), "main", "feature")))
        self.assertEqual(report["comment_lines_added"], 0)
        self.assertEqual(report["failures"], [])

    def test_a_shebang_is_excluded_and_reported(self):
        files = {"bin/tool.sh": "#!/usr/bin/env bash\n" +
                                "".join(f"echo {i}\n" for i in range(10))}
        repo = make_repo(self.tmp, files)
        report = attest.eval_report(_run(attest.diff_text(str(repo), "main", "feature")))
        self.assertEqual(report["comment_lines_added"], 0)
        self.assertEqual(report["excluded"]["shebangs"], 1)
        self.assertEqual(report["failures"], [])

    def test_c_family_block_comments_count_but_pointer_deref_does_not(self):
        report = attest.eval_report(
            "+++ b/src/a.ts\n+// a line comment\n+/* opening */\n+ * continuation\n"
            "+const x = 1;\n"
            "+++ b/src/b.c\n+*ptr = value;\n")
        self.assertEqual(report["comment_lines_added"], 3)
        self.assertEqual(report["production_lines_added"], 5)

    def test_patching_calls_fail_the_eval(self):
        for line in ("    monkeypatch.setattr(mod, 'x', 1)",
                     "    monkeypatch.setenv('A', 'b')",
                     "    with mock.patch('mod.thing'):",
                     "    fake = MagicMock()"):
            with self.subTest(line):
                report = attest.eval_report(
                    f"+++ b/tests/test_a.py\n+{line}\n")
                self.assertEqual(len(report["patching_calls"]), 1, report)
                self.assertTrue(report["failures"])

    def test_a_mention_is_not_a_call(self):
        """Every one of these was a false positive on this skill's own diff."""
        mentions = [
            ("src/a.py", "# we forbid monkeypatch.setattr in production"),
            ("src/a.py", '    r"|\\bMagicMock\\b")'),
            ("src/a.py", '''    for line in ("    monkeypatch.setattr(m, 'x', 1)",'''),
            ("src/a.py", '''    "    with mock.patch('mod.thing'):",'''),
            ("src/a.ts", "  // mock.patch( is banned here"),
            # Prose inside a docstring, which a per-line scan cannot see as a
            # string - the backtick is what gives it away.
            ("src/a.py", "    naming `mock.patch(` in a docstring is not a call"),
        ]
        for path, line in mentions:
            with self.subTest(line):
                report = attest.eval_report(f"+++ b/{path}\n+{line}\n")
                self.assertEqual(report["patching_calls"], [], report)

    def test_a_real_call_still_counts_even_with_a_trailing_comment(self):
        report = attest.eval_report(
            "+++ b/tests/test_a.py\n+    with mock.patch('mod.thing'):  # noqa\n")
        self.assertEqual(len(report["patching_calls"]), 1, report)

    def test_a_pattern_in_a_multiline_string_still_counts_and_is_documented(self):
        """A per-line scan cannot see a triple-quoted string; named, not hidden."""
        report = attest.eval_report(
            '''+++ b/src/a.py\n+    doc = """\n+    MagicMock is mentioned here\n''')
        self.assertEqual(len(report["patching_calls"]), 1, report)

    def test_few_comment_lines_pass_however_bad_the_ratio(self):
        """A ratio alone punishes small, type-level changes; the floor is the fix."""
        report = attest.eval_report(
            "+++ b/src/a.py\n" + "".join(f"+# reason {i}\n" for i in range(6))
            + "+x: Final[int] = 1\n")
        self.assertEqual(report["comment_lines_added"], 6)
        self.assertGreater(report["comment_ratio_pct"], 3.0)
        self.assertEqual(report["failures"], [])

    def test_one_line_over_the_floor_with_a_bad_ratio_fails(self):
        report = attest.eval_report(
            "+++ b/src/a.py\n" + "".join(f"+# reason {i}\n" for i in range(7))
            + "+x: Final[int] = 1\n")
        self.assertEqual(report["comment_lines_added"], 7)
        self.assertTrue(report["failures"])
        self.assertIn("floor", report["failures"][0])

    def test_many_comment_lines_at_a_good_ratio_pass(self):
        report = attest.eval_report(
            "+++ b/src/a.py\n" + "".join(f"+# reason {i}\n" for i in range(20))
            + "".join(f"+x{i} = {i}\n" for i in range(2000)))
        self.assertEqual(report["comment_lines_added"], 20)
        self.assertEqual(report["failures"], [])

    def test_chdir_and_syspath_prepend_are_excluded_not_counted(self):
        report = attest.eval_report(
            "+++ b/tests/test_a.py\n+    monkeypatch.chdir(tmp_path)\n"
            "+    monkeypatch.syspath_prepend(str(src))\n")
        self.assertEqual(report["patching_calls"], [])
        self.assertEqual(report["failures"], [])
        self.assertEqual(len(report["excluded"]["cwd_and_syspath_plumbing"]), 2)

    def test_markdown_prose_is_neither_counted_nor_scanned(self):
        report = attest.eval_report(
            "+++ b/SKILL.md\n+`eval_passed()` rejects `mock.patch(` and MagicMock.\n"
            "+# A markdown heading is not a comment.\n")
        self.assertEqual(report["production_lines_added"], 0)
        self.assertEqual(report["patching_calls"], [])
        self.assertEqual(report["excluded"]["non_code_lines"], 2)
        self.assertEqual(report["failures"], [])

    def test_a_wordless_separator_comment_is_excluded(self):
        report = attest.eval_report(
            "+++ b/src/a.py\n+# " + "-" * 60 + "\n+# a real explanation\n+x = 1\n")
        self.assertEqual(report["comment_lines_added"], 1)
        self.assertEqual(report["excluded"]["separator_comments"], 1)

    def test_an_empty_diff_reports_a_zero_ratio_rather_than_dividing_by_zero(self):
        report = attest.eval_report("")
        self.assertEqual(report["comment_ratio_pct"], 0.0)
        self.assertEqual(report["failures"], [])


class ThresholdsTest(AttestTestCase):
    def test_defaults_apply_with_no_file(self):
        self.assertEqual(attest.thresholds(), attest.DEFAULT_THRESHOLDS)
        self.assertIsNone(attest.eval_report("")["thresholds_file"])

    def test_the_thresholds_file_overrides_the_defaults(self):
        files = {"src/app.py": "".join(
            [f"# explaining line {i}\nvalue_{i} = {i}\n" for i in range(20)])}
        repo = make_repo(self.tmp, files)
        diff = _run(attest.diff_text(str(repo), "main", "feature"))
        self.assertTrue(attest.eval_report(diff)["failures"])

        path = attest.thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"comment_ratio_max_pct": 90.0}))
        relaxed = attest.eval_report(diff)
        self.assertEqual(relaxed["failures"], [])
        self.assertEqual(relaxed["thresholds"]["comment_ratio_max_pct"], 90.0)
        # The unset threshold keeps its embedded default rather than vanishing.
        self.assertEqual(relaxed["thresholds"]["patching_calls_max"],
                         attest.DEFAULT_THRESHOLDS["patching_calls_max"])
        self.assertEqual(relaxed["thresholds_file"], str(path))

    def test_an_unknown_threshold_key_is_rejected_loudly(self):
        path = attest.thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"comment_ratio_maxx": 90.0}))
        with self.assertRaises(attest.AttestError) as ctx:
            attest.thresholds()
        self.assertIn("unknown threshold", str(ctx.exception))


class BaseAnchoringTest(unittest.TestCase):
    """The base a claim is measured against must come from the remote.

    fayhealthinc/fay-service#7373: `base="main"` resolved to a stale local
    `main`, so the merge base was an old tip and the eval scored other people's
    merged commits - and then signed that result.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.remote = tmp / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.remote)],
                       check=True, capture_output=True)
        self.repo = tmp / "repo"
        self.repo.mkdir()
        _git(self.repo.parent, "init", "-q", "-b", "main", str(self.repo))
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "remote", "add", "origin", str(self.remote))
        (self.repo / "README.md").write_text("start\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "initial")
        _git(self.repo, "push", "-q", "origin", "main")
        self.old_main = _git(self.repo, "rev-parse", "main").strip()
        # Somebody else's work lands on main...
        (self.repo / "their_feature.py").write_text("# 20 lines of theirs\n" * 20)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "someone else's merge")
        _git(self.repo, "push", "-q", "origin", "main")
        self.new_main = _git(self.repo, "rev-parse", "main").strip()
        # ...our branch is cut from the up-to-date main...
        _git(self.repo, "checkout", "-q", "-b", "feature")
        (self.repo / "ours.py").write_text("value = 1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "ours")
        # ...and our local `main` is then left behind, which is the normal state
        # of a long-lived checkout.
        _git(self.repo, "update-ref", "refs/heads/main", self.old_main)

    def test_a_stale_local_main_does_not_drag_other_peoples_commits_into_the_diff(self):
        resolved = _run(attest.resolve_diff(str(self.repo), "main", "feature"))
        self.assertEqual(resolved["base_sha"], self.new_main)
        self.assertEqual(resolved["merge_base"], self.new_main)
        self.assertEqual(resolved["base_how"], "origin/main")
        self.assertIn("ours.py", resolved["diff"])
        self.assertNotIn("their_feature.py", resolved["diff"])

    def test_the_stale_local_ref_really_would_have_measured_the_wrong_diff(self):
        """The failing direction: without remote anchoring, the same call is wrong.

        Asserting the fix without asserting the bug leaves no evidence the
        anchoring is load-bearing.
        """
        stale = _git(self.repo, "diff", "--no-color", f"{self.old_main}...feature")
        self.assertIn("their_feature.py", stale)
        resolved = _run(attest.resolve_diff(str(self.repo), "main", "feature"))
        self.assertNotEqual(
            hashlib_sha256(stale), hashlib_sha256(resolved["diff"]),
            "the stale-ref diff and the anchored diff must not be the same bytes")

    def test_a_local_base_the_remote_does_not_have_is_refused_not_guessed(self):
        _git(self.repo, "checkout", "-q", "main")
        _git(self.repo, "reset", "-q", "--hard", self.new_main)
        (self.repo / "local_only.py").write_text("x = 1\n")
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-qm", "local only commit")
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.resolve_diff(str(self.repo), "main", "feature"))
        self.assertIn("ambiguous", str(ctx.exception))

    def test_an_unfetchable_base_with_a_configured_origin_raises(self):
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.resolve_diff(str(self.repo), "no-such-branch", "feature"))
        message = str(ctx.exception)
        self.assertIn("cannot anchor the base", message)
        self.assertIn("no-such-branch", message)

    def test_an_explicit_sha_base_is_taken_as_given(self):
        resolved = _run(attest.resolve_diff(str(self.repo), self.new_main, "feature"))
        self.assertEqual(resolved["base_sha"], self.new_main)
        self.assertEqual(resolved["base_how"], "explicit sha")

    def test_the_issued_token_records_the_shas_it_measured(self):
        os.environ["ATTEST_HOME"] = str(Path(self._tmp.name) / "state")
        self.addCleanup(os.environ.pop, "ATTEST_HOME", None)
        token = _run(attest.eval_passed(str(self.repo), "main", "feature"))
        payload = attest.decode(token)
        self.assertEqual(payload["base_sha"], self.new_main)
        self.assertEqual(payload["merge_base"], self.new_main)
        self.assertEqual(payload["head_sha"],
                         _git(self.repo, "rev-parse", "feature").strip())
        self.assertEqual(token.report["revisions"]["base_how"], "origin/main")
        record = json.loads(attest.log_path().read_text().strip().splitlines()[-1])
        self.assertEqual(record["base_sha"], self.new_main)


def hashlib_sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == "__main__":
    unittest.main()
