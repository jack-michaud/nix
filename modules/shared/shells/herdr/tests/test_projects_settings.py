"""Synthetic settings contracts only: no live board command or mutation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("projects_settings", ROOT / "config/projects_settings.py")
settings = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(settings)
KEY = settings.KEY

MOCK = '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ["CALLS"]).open("a") as f:
    f.write(json.dumps(args) + "\\n")
mode = os.environ.get("MODE", "")
if args == ["version"]:
    print("herdr-projects " + ("1.2.2" if mode == "old" else "1.2.26") + " (/fixture)")
    sys.exit()
assert args[0] == "show" and args[-1] == "--json", args
if mode == "unavailable" or (mode == "partial" and "--machine-coordinator" in args):
    print("PRIVATE TEXT MUST NOT LEAK", file=sys.stderr)
    sys.exit(7)
if mode == "malformed":
    print("not JSON")
    sys.exit()
config = json.loads(Path(os.environ["RUNTIME"]).read_text())
local = config
place = "you"
if "--main-coordinator" in args:
    local = config["coordinators"]["main"]
    place = "coord"
elif "--machine-coordinator" in args:
    local = config["coordinators"]["machine"]
    place = "coord"
elif "--project-coordinator" in args:
    local = config["coordinators"]["projects"][args[2]]
    place = "coord"
raw = local.get("coordinator", {}).get("instructions")
default = config.get("coordinator", {}).get("instructions")
# Independent source-contract model of values.rs::Ty::Text and lookup.rs.
# Rust Unicode White_Space is narrower than Python's default strip set.
whitespace = "".join(chr(cp) for cp in [9, 10, 11, 12, 13, 32, 133, 160, 5760,
                                     *range(8192, 8203), 8232, 8233, 8239, 8287, 12288])
parts = []
for value in ([default] if local is config else [default, raw]):
    if value is None:
        continue
    checked = value.strip(whitespace)
    assert checked, "invalid runtime text"
    if checked.lower() == "none":
        parts.clear()
    else:
        parts.append(checked)
effective = "\\n\\n".join(parts) if parts else "none"
if raw is None:
    place = "you" if default is not None else "builtin"
row = {"name": "coordinator.instructions", "value": effective,
       "own": raw is not None, "place": place, "note": ""}
if mode == "wrong-scope":
    row["own"] = not row["own"]
if mode == "wrong-value":
    row["value"] = "wrong"
print(json.dumps({"settings": [row], "problems": ["bad"] if mode == "problems" else []}))
'''


def manifest(**scopes):
    return {"version": 1, "scopes": {s: {KEY: v} for s, v in scopes.items()}}


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = {
            "coordinator": {"instructions": "OWNER REPORTING POLICY", "agent": "pi", "access": "full"},
            "board": {"notify": "unmanaged"}, "repos": {"dotfiles": {"merge": {"by": "you"}}},
            "coordinators": {"main": {"coordinator": {"instructions": "custom main"}},
                             "machine": {}, "projects": {"dotfiles": {"coordinator": {"instructions": "custom project"}, "autopilot": {"every": "6h"}}}}}
        self.runtime = self.root / "runtime.json"
        self.runtime.write_text(json.dumps(self.config))
        self.declaration = self.root / "manifest.json"
        self.declaration.write_text(json.dumps(manifest(defaults="shared", main="main-only", **{"project:dotfiles": "project-only"})))
        self.board = self.root / "board"
        self.board.write_text("#!" + sys.executable + "\n" + MOCK)
        self.board.chmod(0o755)
        self.env = os.environ | {"CALLS": str(self.root / "calls"), "RUNTIME": str(self.runtime)}

    def run_helper(self, command="plan", **env):
        return subprocess.run([sys.executable, str(ROOT / "config/projects_settings.py"), command,
                               "--manifest", str(self.declaration), "--settings", str(self.runtime),
                               "--board", str(self.board)], env=self.env | env, text=True,
                              capture_output=True, timeout=10)

    def test_plan_idempotent_without_cli_or_mutable_writes(self):
        before = self.runtime.read_bytes()
        first, second = self.run_helper(), self.run_helper()
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(self.runtime.read_bytes(), before)
        self.assertFalse((self.root / "calls").exists())
        self.assertNotIn("OWNER REPORTING POLICY", first.stdout)
        self.assertNotIn("custom main", first.stdout)

    def test_preserve_reporting_custom_text_and_add_once(self):
        first = settings.compose("OWNER REPORTING POLICY\ncustom", "shared", "defaults")
        self.assertTrue(first.startswith("OWNER REPORTING POLICY\ncustom\n\n"))
        self.assertEqual(first.count("shared"), 1)
        self.assertEqual(settings.compose(first, "shared", "defaults"), first)
        project = settings.compose("custom project", "project-only", "project:dotfiles")
        self.assertEqual(settings.effective(first, project).count("shared"), 1)
        self.assertNotIn("shared", project)

    def test_removal_and_rollback_preview_preserve_newer_custom_bytes(self):
        managed = settings.compose("original", "old", "defaults")
        newer = managed + "\nnew runtime work"
        changed = settings.compose(newer, "new", "defaults")
        self.assertTrue(changed.endswith("\nnew runtime work"))
        removed = settings.compose(changed, "", "defaults")
        self.assertEqual(removed, "original\nnew runtime work")
        rollback = settings.compose(changed, "old", "defaults")
        self.assertEqual(rollback, newer)
        self.assertEqual(settings.compose(newer, None, "defaults"), newer)

    def test_scoped_none_suppression_is_preserved(self):
        self.assertEqual(settings.effective("shared", "none"), "none")
        with self.assertRaises(settings.Refused):
            settings.compose("none", "addition", "main")
        self.assertEqual(settings.compose("none", "", "main"), "none")

    def test_normalized_reset_tokens_refuse_scoped_additions_without_losing_raw_text(self):
        for token in ("none", " NONE ", "NoNe", "\u2003NoNe\u2029"):
            with self.subTest(token=token):
                self.assertEqual(settings.normalized_text(token), "none")
                self.assertEqual(settings.effective("shared", token), "none")
                self.assertEqual(settings.compose(token, None, "main"), token)
                self.assertEqual(settings.compose(token, "", "main"), token)
                with self.assertRaises(settings.Refused):
                    settings.compose(token, "addition", "main")
                config = copy.deepcopy(self.config)
                config["coordinators"]["main"]["coordinator"]["instructions"] = token
                row = next(r for r in settings.preview(manifest(), config)["scopes"] if r["scope"] == "main")
                self.assertEqual(row["proposedEffectiveHash"], settings.digest("none"))
                self.assertEqual(row["proposedOwnHash"], settings.digest(token))
                self.assertFalse(row["change"])
                with self.assertRaises(settings.Refused):
                    settings.preview(manifest(main="addition"), config)
                self.assertNotIn(token, settings.compose(token, "addition", "defaults"))
        for token in (" NONE ", "NoNe", "\u2003NONE\u2029"):
            with self.subTest(declaration=token), self.assertRaises(settings.Refused):
                settings.validate_manifest(manifest(main=token))

    def test_normalized_effective_preview_preserves_unmanaged_raw_bytes(self):
        raw = " \towner reporting policy\n"
        config = copy.deepcopy(self.config)
        config["coordinator"]["instructions"] = raw
        config["coordinators"]["main"]["coordinator"]["instructions"] = "\u2003local policy\n"
        before = copy.deepcopy(config)
        rows = {r["scope"]: r for r in settings.preview(manifest(), config)["scopes"]}
        self.assertEqual(settings.own(config, "defaults"), raw)
        self.assertEqual(rows["defaults"]["beforeHash"], settings.digest(raw))
        self.assertEqual(rows["defaults"]["proposedOwnHash"], settings.digest(raw))
        self.assertFalse(rows["defaults"]["change"])
        self.assertEqual(rows["defaults"]["proposedEffectiveHash"], settings.digest("owner reporting policy"))
        self.assertEqual(rows["main"]["proposedEffectiveHash"], settings.digest("owner reporting policy\n\nlocal policy"))
        composed = settings.compose(raw, "managed addition", "defaults")
        self.assertTrue(composed.startswith(raw + "\n\n"))
        self.assertEqual(settings.compose(composed, "", "defaults"), raw)
        self.assertEqual(config, before)

    def test_rust_whitespace_contract_and_invalid_empty_text(self):
        self.assertEqual(settings.normalized_text("\u0085\u00a0\u1680\u200aPolicy\u202f\u205f\u3000"), "Policy")
        # Python strip would drop these control characters; Rust trim does not.
        self.assertEqual(settings.normalized_text("\x1cNONE\x1f"), "\x1cNONE\x1f")
        for text in ("", " \n\t", "\u2003\u2029"):
            with self.subTest(text=text), self.assertRaises(settings.Refused):
                settings.effective(text)
            config = {"coordinator": {"instructions": text}}
            with self.assertRaises(settings.Refused):
                settings.preview(manifest(), config)

    def test_readback_accepts_normalized_text_and_reset_provenance(self):
        self.declaration.write_text(json.dumps(manifest()))
        for default, local, expected in [
                (" owner reporting policy\n", None, "owner reporting policy"),
                ("\u2003owner policy\n", "\tlocal policy\u2029", "owner policy\n\nlocal policy"),
                (" owner policy ", " NONE ", "none"),
                ("\u2003NoNe\u2029", " local policy ", "local policy"),
                (" NoNe ", None, "none"),
                ("\x1cNONE\x1f", None, "\x1cNONE\x1f")]:
            with self.subTest(default=default, local=local):
                config = copy.deepcopy(self.config)
                config["coordinator"]["instructions"] = default
                config["coordinators"]["main"] = {} if local is None else {"coordinator": {"instructions": local}}
                self.runtime.write_text(json.dumps(config))
                before = self.runtime.read_bytes()
                result = self.run_helper("readback")
                self.assertEqual(result.returncode, 0, result.stderr)
                main = next(r for r in json.loads(result.stdout)["scopes"] if r["scope"] == "main")
                self.assertEqual(main["effectiveHash"], settings.digest(expected))
                self.assertEqual(self.runtime.read_bytes(), before)
                rejected = self.run_helper("readback", MODE="wrong-scope")
                self.assertNotEqual(rejected.returncode, 0)

    def test_machine_is_not_parent_of_project_settings(self):
        declared = manifest(defaults="D", machine="M", **{"project:dotfiles": "P"})
        rows = settings.preview(declared, self.config)["scopes"]
        projected = next(r for r in rows if r["scope"] == "project:dotfiles")
        expected = settings.effective(settings.compose("OWNER REPORTING POLICY", "D", "defaults"),
                                      settings.compose("custom project", "P", "project:dotfiles"))
        self.assertEqual(projected["proposedEffectiveHash"], settings.digest(expected))

    def test_unknown_keys_values_scopes_and_duplicates_fail(self):
        values = [manifest(defaults="none"), manifest(defaults=" "), manifest(defaults=4),
                  manifest(defaults=settings.OPEN), manifest(**{"project:$(bad)": "x"}),
                  {"version": 2, "scopes": {}}, {"version": 1, "scopes": {"main": {"coordinator.agent": "codex"}}}]
        for value in values:
            with self.subTest(value=value), self.assertRaises(settings.Refused):
                settings.preview(value, self.config)
        with self.assertRaises(settings.Refused):
            settings.preview(manifest(defaults="shared", main="copy shared copy"), self.config)
        self.declaration.write_text('{"version":1,"version":1,"scopes":{}}')
        self.assertNotEqual(self.run_helper().returncode, 0)

    def test_malformed_runtime_and_markers_fail_without_cli(self):
        for text in ("{", "[]", '{"coordinator":{"instructions":4}}',
                     json.dumps({"coordinator": {"instructions": settings.CLOSE}})):
            self.runtime.write_text(text)
            self.assertNotEqual(self.run_helper().returncode, 0)
        self.assertFalse((self.root / "calls").exists())

    def test_exact_scoped_readback_and_provenance(self):
        result = self.run_helper("readback")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(s) for s in (self.root / "calls").read_text().splitlines()]
        self.assertEqual(calls, [["version"], ["show", "--json"], ["show", "--machine-coordinator", "--json"],
                                ["show", "--main-coordinator", "--json"], ["show", "--project-coordinator", "dotfiles", "--json"]])
        self.assertEqual(self.config, json.loads(self.runtime.read_text()))

    def test_partial_failure_unavailable_old_version_and_bad_readback_never_mutate(self):
        for mode in ("partial", "unavailable", "old", "malformed", "wrong-scope", "wrong-value", "problems"):
            with self.subTest(mode=mode):
                result = self.run_helper("readback", MODE=mode)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("PRIVATE TEXT", result.stdout + result.stderr)
                self.assertEqual(self.config, json.loads(self.runtime.read_text()))
        calls = [json.loads(s) for s in (self.root / "calls").read_text().splitlines()]
        self.assertTrue(all(c[0] in ("version", "show") for c in calls))

    def test_apply_refuses_with_context_intact_without_calling_board(self):
        result = self.run_helper("apply", HERDR_PROJECTS_ID="dotfiles/4")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Task-tagged", result.stderr)
        self.assertFalse((self.root / "calls").exists())
        self.assertEqual(self.config, json.loads(self.runtime.read_text()))

    def test_unrelated_mutable_state_and_omitted_declarations_unchanged(self):
        before = copy.deepcopy(self.config)
        task = self.root / "task.json"
        task.write_text('{"history":"newer runtime work"}')
        settings.preview(manifest(main="only-main"), self.config)
        self.assertEqual(before, self.config)
        self.assertEqual(task.read_text(), '{"history":"newer runtime work"}')


if __name__ == "__main__":
    unittest.main()
