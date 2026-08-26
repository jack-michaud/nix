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
                           ("ATTEST_HOME", "ATTEST_LINEAR_ENDPOINT", "LINEAR_API_KEY",
                            "ATTEST_HUMANIZER")}
        os.environ["ATTEST_HOME"] = str(self.tmp / "state")
        os.environ["LINEAR_API_KEY"] = "lin_api_test"
        os.environ.pop("ATTEST_LINEAR_ENDPOINT", None)
        # Cleared, so this machine's real humanizer - present or not - cannot
        # change what the suite measures.
        os.environ.pop("ATTEST_HUMANIZER", None)

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


    def test_a_file_path_is_read_from_disk_with_no_linear_involved(self):
        # No serve_design: a working Linear is deliberately absent.
        doc = self.tmp / "spec.md"
        doc.write_text(DESIGN)
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.design_reviewed(
            repo=str(repo), base="main", head="feature",
            design_doc_id=str(doc),
            quote="The queue must release its slot when no announcement is eligible.",
            requirements=[("release the slot", "src/app.py:3")]))
        payload = attest.decode(token)
        self.assertEqual(payload["claim"], "design_reviewed")
        self.assertEqual(payload["doc_id"], str(doc))
        self.assertEqual(token.report["doc"]["url"], doc.resolve().as_uri())

    def test_a_quote_matches_inside_an_exported_html_plan(self):
        doc = self.tmp / "plan.html"
        doc.write_text("<h2>Rules</h2><p>The queue must release its slot\n"
                       "when no announcement is eligible.</p>")
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.design_reviewed(
            repo=str(repo), base="main", head="feature",
            design_doc_id=str(doc),
            quote="The queue must release its slot when no announcement is eligible.",
            requirements=[("release the slot", "src/app.py:3")]))
        self.assertEqual(attest.decode(token)["claim"], "design_reviewed")

    def test_an_empty_design_file_raises(self):
        doc = self.tmp / "spec.md"
        doc.write_text("   \n")
        repo = make_repo(self.tmp, CLEAN_FILES)
        with self.assertRaises(attest.AttestError) as ctx:
            _run(attest.design_reviewed(
                repo=str(repo), base="main", head="feature",
                design_doc_id=str(doc), quote="anything",
                requirements=[("x", "src/app.py:1")]))
        self.assertIn("empty", str(ctx.exception))

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


# A real humanizer module, deterministic and inference-free, written to disk and
# loaded through ATTEST_HUMANIZER. It is built to the shared contract: keep the
# first two paragraphs, carry every Shipped-With: trailer through byte-exact,
# and score on length so a long text scores badly.
STUB_HUMANIZER = r"""import re

TRAILER = re.compile(r"(?m)^Shipped-With:.*$")


def score(text):
    return {"slop_score": min(1.0, len(text) / 8000.0),
            "signals": {"chars": len(text)}, "too_long": len(text) > 6000}


RUN = {"attempts": 1, "succeeded": 1, "degraded": False, "failures": [],
       "duration_ms": 12, "attempted_at": "2026-08-26T00:00:00Z"}


def humanize(text, context=None):
    preserved = TRAILER.findall(text)
    kept = [p for p in TRAILER.sub("", text).strip().split("\n\n") if p.strip()][:2]
    out = "\n\n".join(kept + preserved)
    return {"text": out, "changed": out != text, "reason": "kept two paragraphs",
            "metrics": {"chars_before": len(text), "chars_after": len(out),
                        "words_before": len(text.split()),
                        "words_after": len(out.split()),
                        "slop_score": score(out)["slop_score"]},
            "preserved": preserved, "run": dict(RUN),
            "a_key_attest_has_never_heard_of": "tolerated"}
"""

# Three humanizers that fail in the three ways a real one can.
TRAILER_EATING_HUMANIZER = STUB_HUMANIZER.replace(
    r'out = "\n\n".join(kept + preserved)', r'out = "\n\n".join(kept)')
STUBBORN_HUMANIZER = STUB_HUMANIZER.replace(
    r'out = "\n\n".join(kept + preserved)', "out = text")
# Inference was attempted twice and failed twice: text unchanged, degraded TRUE.
# The text is identical to an "already clean" verdict and means the opposite.
DEGRADED_HUMANIZER = STUBBORN_HUMANIZER.replace(
    '"attempts": 1, "succeeded": 1, "degraded": False, "failures": []',
    '"attempts": 2, "succeeded": 0, "degraded": True, "failures": ["timeout", "timeout"]')
BROKEN_HUMANIZER = STUB_HUMANIZER.replace(
    "    preserved = TRAILER.findall(text)",
    "    raise RuntimeError('no inference endpoint configured')")

TRAILER_LINE = "Shipped-With: jj_ship/0.2.0 attest=1a2b3c4d5e6f,0f9e8d7c6b5a"

SHORT_HUMAN_BODY = (
    attest.DISCLOSURE_LINE + "\n\n"
    "Bumps the pin to 1.4.2 and drops the workaround it existed for.\n\n"
    "Ran the suite locally. Nothing else changed.\n")


def slop(paragraphs: int) -> str:
    """A description in the shape this check exists for: jack-michaud/nix#27 was
    about 13000 characters of exactly this."""
    return "\n\n".join(
        f"### Section {n}\n\nThis section comprehensively describes the changes "
        f"in a robust and holistic manner, ensuring that the reader is fully "
        f"empowered to understand the seamless end-to-end implementation."
        for n in range(paragraphs))


# Long enough to be scored, short and plain enough to pass: the ordinary case.
MID_HUMAN_BODY = attest.DISCLOSURE_LINE + "\n\n" + "\n\n".join(
    f"Step {n}: read the file, changed the two lines that were wrong, and ran "
    f"the tests. The old behaviour is kept behind the same flag as before."
    for n in range(8))


class DescriptionHumanizedTest(AttestTestCase):
    """The third claim: the description a human is asked to read.

    Every humanizer here is a real module on disk behind ATTEST_HUMANIZER, for
    the same reason the Linear fetch is a real HTTP server - eval_passed()
    counts `mock.patch(`/`MagicMock` as violations, so this suite has to pass
    the gate it extends.
    """

    def install_humanizer(self, source: str = STUB_HUMANIZER) -> Path:
        path = self.tmp / "humanizer_stub.py"
        path.write_text(source)
        os.environ["ATTEST_HUMANIZER"] = str(path)
        return path

    def test_a_short_human_description_is_never_flagged(self):
        """The false positive that would matter most: Jack's own two-liner."""
        self.install_humanizer()
        report = attest.humanize_body(SHORT_HUMAN_BODY)
        self.assertFalse(report["flagged"])
        self.assertFalse(report["humanized"])
        self.assertIsNone(report["slop_score_before"])  # not scored at all
        self.assertEqual(report["body"], SHORT_HUMAN_BODY)
        self.assertIn("floor", report["reason"])

    def test_plain_prose_over_the_floor_is_scored_and_left_alone(self):
        self.install_humanizer()
        report = attest.humanize_body(MID_HUMAN_BODY)
        self.assertGreater(report["chars_before"],
                           attest.DEFAULT_THRESHOLDS["description_short_chars"])
        self.assertIsNotNone(report["slop_score_before"])
        self.assertFalse(report["flagged"])
        self.assertEqual(report["body"], MID_HUMAN_BODY)

    def test_the_trailer_and_the_disclosure_survive_the_rewrite(self):
        """Losing either one is silent damage: ship-check reads the PR body and
        nothing else, and the disclosure is policy on every public artifact."""
        self.install_humanizer()
        body = f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}\n\n{TRAILER_LINE}\n"
        report = attest.humanize_body(body)
        self.assertTrue(report["humanized"])
        self.assertIn(TRAILER_LINE, report["body"])
        self.assertTrue(attest.has_disclosure(report["body"]))
        self.assertEqual(report["preserved"], [TRAILER_LINE])
        self.assertLess(report["chars_after"], report["chars_before"])

    def test_a_rewrite_that_drops_the_trailer_is_refused_not_repaired(self):
        self.install_humanizer(TRAILER_EATING_HUMANIZER)
        body = f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}\n\n{TRAILER_LINE}\n"
        with self.assertRaises(attest.AttestError) as ctx:
            attest.humanize_body(body, enforce=True)
        self.assertIn("dropped the attestation trailer", str(ctx.exception))
        # ...and the body handed back is the INPUT, never the damaged rewrite.
        advisory = attest.humanize_body(body, enforce=False)
        self.assertFalse(advisory["passed"])
        self.assertIn(TRAILER_LINE, advisory["body"])

    def test_a_missing_disclosure_is_added_rather_than_refused(self):
        self.install_humanizer()
        report = attest.humanize_body("Bumps the pin to 1.4.2.\n")
        self.assertTrue(report["disclosure_added"])
        self.assertTrue(report["body"].startswith(attest.DISCLOSURE_LINE))
        self.assertIn("Bumps the pin to 1.4.2.", report["body"])

    def test_a_rewrite_that_is_still_over_the_line_raises(self):
        self.install_humanizer(STUBBORN_HUMANIZER)
        with self.assertRaises(attest.AttestError) as ctx:
            attest.humanize_body(f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}", enforce=True)
        message = str(ctx.exception)
        self.assertIn("characters after the rewrite", message)
        self.assertIn("The humanizer said: kept two paragraphs", message)
        self.assertIn("Editing it by hand", message)

    def test_a_humanizer_that_cannot_run_stops_only_a_flagged_description(self):
        """Inference down. A description that needed no rewrite never needed it."""
        self.install_humanizer(BROKEN_HUMANIZER)
        with self.assertRaises(attest.AttestError) as ctx:
            attest.humanize_body(f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}", enforce=True)
        self.assertIn("could not run", str(ctx.exception))
        self.assertFalse(attest.humanize_body(MID_HUMAN_BODY)["flagged"])

    def test_with_no_humanizer_at_all_the_claim_covers_length_only(self):
        os.environ["ATTEST_HUMANIZER"] = str(self.tmp / "no-humanizer-here.py")
        report = attest.humanize_body(MID_HUMAN_BODY)
        self.assertIn("LENGTH ONLY", report["reason"])
        self.assertTrue(report["humanizer"].startswith("unavailable"))
        self.assertIsNone(report["slop_score_before"])
        with self.assertRaises(attest.AttestError) as ctx:
            attest.humanize_body(f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}", enforce=True)
        self.assertIn("no humanizer is available", str(ctx.exception))

    def test_running_the_gate_on_its_own_output_changes_nothing(self):
        self.install_humanizer()
        once = attest.humanize_body(
            f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}\n\n{TRAILER_LINE}\n")
        twice = attest.humanize_body(once["body"])
        self.assertEqual(twice["body"], once["body"])
        self.assertFalse(twice["humanized"])

    def test_the_short_floor_and_the_limits_are_configurable(self):
        self.install_humanizer()
        path = attest.thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"description_short_chars": 10}))
        report = attest.humanize_body(SHORT_HUMAN_BODY)
        self.assertIsNotNone(report["slop_score_before"])  # now scored
        self.assertFalse(report["flagged"])
        self.assertEqual(report["thresholds"]["description_short_chars"], 10)

    def test_the_token_binds_the_body_that_will_be_posted(self):
        self.install_humanizer()
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.description_humanized(
            str(repo), "main", "feature", SHORT_HUMAN_BODY))
        payload = attest.decode(token)
        self.assertEqual(payload["claim"], "description_humanized")
        self.assertEqual(payload["body_sha"], attest.body_sha(SHORT_HUMAN_BODY))
        sha = payload["diff_sha"]
        required = ("description_humanized",)
        attest.verify([token], sha, required=required, body=token.report["body"])
        with self.assertRaises(attest.AttestError) as ctx:
            attest.verify([token], sha, required=required,
                          body=token.report["body"] + "\n\nAnd a claim nobody attested to.")
        self.assertIn("bound to a different body", str(ctx.exception))
        self.assertTrue(attest.body_matches(token, token.report["body"]))
        self.assertFalse(attest.body_matches(token, "something else entirely"))

    def test_the_trailer_and_crlf_do_not_change_the_body_hash(self):
        """jj_ship appends the trailer AFTER this token exists - it names the
        token - and GitHub hands bodies back CRLF-terminated."""
        posted = SHORT_HUMAN_BODY + "\n" + TRAILER_LINE + "\n"
        self.assertEqual(attest.body_sha(posted), attest.body_sha(SHORT_HUMAN_BODY))
        self.assertEqual(attest.body_sha(SHORT_HUMAN_BODY.replace("\n", "\r\n")),
                         attest.body_sha(SHORT_HUMAN_BODY))
        self.assertNotEqual(attest.body_sha(posted + "one more sentence."),
                            attest.body_sha(SHORT_HUMAN_BODY))

    def test_by_default_the_claim_is_advisory_and_blocks_nothing(self):
        """Amendment 1: until the scorer is shown to measure slop rather than
        length, this check must not be able to refuse a ship on any machine."""
        self.install_humanizer(STUBBORN_HUMANIZER)
        self.assertEqual(attest.required_claims(), attest.BASE_CLAIMS)
        self.assertNotIn(attest.DESCRIPTION_CLAIM, attest.required_claims())
        report = attest.humanize_body(f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}")
        self.assertFalse(report["enforced"])
        self.assertFalse(report["passed"])
        self.assertTrue(report["failures"])

    def test_an_advisory_run_still_records_the_whole_signal_vector(self):
        """Amendment 2: advisory must mean RECORDED. A silent check proves
        nothing and builds no dataset."""
        self.install_humanizer()
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.description_humanized(
            str(repo), "main", "feature", MID_HUMAN_BODY))
        payload = attest.decode(token)
        self.assertEqual(payload["claim"], attest.DESCRIPTION_CLAIM)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["body_sha"], attest.body_sha(MID_HUMAN_BODY))
        record = json.loads(attest.log_path().read_text().strip().splitlines()[-1])
        self.assertEqual(record["report"]["signals_before"]["signals"]["chars"],
                         report_chars(MID_HUMAN_BODY))
        self.assertIsNotNone(record["report"]["slop_score_before"])

    def test_an_advisory_failure_is_issued_but_cannot_satisfy_the_claim_later(self):
        self.install_humanizer(STUBBORN_HUMANIZER)
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.description_humanized(
            str(repo), "main", "feature", f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}"))
        self.assertFalse(attest.decode(token)["passed"])
        sha = attest.decode(token)["diff_sha"]
        # Advisory: nothing is required of it, so a ship is not blocked.
        attest.verify([token], sha, required=())
        # After the epoch: the same token cannot stand in for the claim.
        with self.assertRaises(attest.AttestError) as ctx:
            attest.verify([token], sha, required=(attest.DESCRIPTION_CLAIM,),
                          body=token.report["body"])
        self.assertIn("did NOT pass", str(ctx.exception))


    def test_the_rewriters_run_block_is_carried_through_and_extra_keys_are_ok(self):
        """The humanizer contract grew a sixth key. A gate that asserts an exact
        key set breaks on its rewriter's next release, so only named keys are
        read."""
        self.install_humanizer()
        report = attest.humanize_body(
            f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}", enforce=False)
        self.assertTrue(report["humanized"])
        self.assertEqual(report["humanizer_run"]["attempts"], 1)
        self.assertFalse(report["humanizer_run"]["degraded"])
        self.assertEqual(report["humanizer_run"]["attempted_at"],
                         "2026-08-26T00:00:00Z")

    def test_a_degraded_run_is_recorded_as_degraded_not_as_clean(self):
        """Same text, opposite meaning: inference was attempted and every
        attempt failed. The advisory row has to be able to tell them apart."""
        self.install_humanizer(DEGRADED_HUMANIZER)
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.description_humanized(
            str(repo), "main", "feature", f"{attest.DISCLOSURE_LINE}\n\n{slop(40)}"))
        payload = attest.decode(token)
        self.assertTrue(payload["degraded"])
        self.assertFalse(payload["passed"])
        record = json.loads(attest.log_path().read_text().strip().splitlines()[-1])
        run = record["report"]["humanizer_run"]
        self.assertEqual(run["attempts"], 2)
        self.assertEqual(run["succeeded"], 0)
        self.assertEqual(run["failures"], ["timeout", "timeout"])

    def test_not_attempted_is_not_degradation(self):
        """Under the floor, no humanizer, or already within the limits: the
        rewriter was never called, so `degraded` is None rather than False."""
        self.install_humanizer()
        repo = make_repo(self.tmp, CLEAN_FILES)
        for label, body in (("short", SHORT_HUMAN_BODY), ("clean", MID_HUMAN_BODY)):
            with self.subTest(label):
                token = _run(attest.description_humanized(
                    str(repo), "main", "feature", body))
                self.assertIsNone(attest.decode(token)["degraded"])
                self.assertIsNone(token.report["humanizer_run"])
                self.assertTrue(attest.decode(token)["passed"])


class RequiredClaimsEpochTest(AttestTestCase):
    """Adding a claim to a bare tuple invalidates every trailer already
    shipped, because jj_ship and ship_check both read the required set at call
    time. The epoch is what stops a gate change from being retroactive."""

    def turn_on(self, since: str = "2026-08-26T00:00:00Z") -> None:
        path = attest.thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"description_claim_required_since": since}))

    def test_null_means_never_required_anywhere(self):
        self.assertIsNone(
            attest.DEFAULT_THRESHOLDS["description_claim_required_since"])
        self.assertEqual(attest.required_claims(), attest.BASE_CLAIMS)
        self.assertEqual(attest.required_claims(at="2099-01-01T00:00:00Z"),
                         attest.BASE_CLAIMS)

    def test_the_epoch_splits_before_from_after(self):
        self.turn_on()
        self.assertEqual(attest.required_claims(at="2026-08-25T19:16:12Z"),
                         attest.BASE_CLAIMS)
        self.assertEqual(
            attest.required_claims(at="2026-08-26T09:00:00Z"),
            attest.BASE_CLAIMS + (attest.DESCRIPTION_CLAIM,))
        self.assertEqual(attest.required_claims(at=1_798_000_000.0),
                         attest.BASE_CLAIMS + (attest.DESCRIPTION_CLAIM,))

    def test_verify_resolves_the_required_set_at_call_time(self):
        """A default argument would freeze the answer at import; the whole
        rollback that prompted this change was a gate that moved under a fleet
        which had already imported it."""
        repo = make_repo(self.tmp, CLEAN_FILES)
        token = _run(attest.eval_passed(str(repo), "main", "feature"))
        sha = attest.decode(token)["diff_sha"]
        design = str(attest._issue("design_reviewed", sha, str(repo), "main",
                                   "feature", "ENG-1", "q" * 64, 1, {}))
        attest.verify([token, design], sha)          # two claims: enough today
        self.turn_on()
        with self.assertRaises(attest.AttestError) as ctx:
            attest.verify([token, design], sha)
        self.assertIn("description_humanized", str(ctx.exception))

    def test_an_unreadable_epoch_says_so_instead_of_guessing(self):
        path = attest.thresholds_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"description_claim_required_since": "soon"}))
        with self.assertRaises(attest.AttestError) as ctx:
            attest.required_claims()
        self.assertIn("cannot read 'soon' as a time", str(ctx.exception))


def report_chars(text: str) -> int:
    """What the stub humanizer's `chars` signal should say for `text`."""
    return len(attest.canonical_body(text))


def hashlib_sha256(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == "__main__":
    unittest.main()
