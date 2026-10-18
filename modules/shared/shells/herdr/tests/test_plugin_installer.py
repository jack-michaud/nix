"""Run with HERDR_PLUGINS_INSTALLER pointing at the Nix-built installer.

python3 -m unittest discover -s modules/shared/shells/herdr/tests -v
All Herdr calls are mocked; no real registry, server or network is used.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MOCK_HERDR = '''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
state = Path(os.environ["TEST_STATE"])
records = json.loads(state.read_text())
with Path(os.environ["TEST_CALLS"]).open("a") as log:
    log.write(json.dumps(args) + "\\n")
assert sys.stdin.read() == "", "installer must not prompt on stdin"
if args == ["plugin", "list", "--json"]:
    if os.environ.get("TEST_BAD_LIST"):
        print('{"error": "unavailable"}')
    else:
        print(json.dumps({"result": {"plugins": records}}))
elif args[:3] == ["plugin", "install", "--yes"] and len(args) == 4:
    if os.environ.get("TEST_FAIL_INSTALL"):
        sys.exit(7)
    parts = args[3].split("/")
    identity = "/".join(parts[:2]).lower()
    ids = {"nathanflurry/herdr-plugin-jj-workspace": "nathanflurry.jj-workspace",
           "eliasstravik/herdr-projects": "herdr-projects"}
    plugin_id = ids.get(identity, args[3])
    if any(p["plugin_id"] == plugin_id and p["source"]["kind"] == "local" for p in records):
        sys.exit(8)  # Real Herdr refuses to overwrite local links.
    source = {"kind": "github", "owner": parts[0], "repo": parts[1]}
    if len(parts) > 2:
        source["subdir"] = "/".join(parts[2:])
    records.append({"plugin_id": plugin_id, "enabled": True, "source": source})
    state.write_text(json.dumps(records))
elif args[:2] == ["plugin", "unlink"] and len(args) == 3:
    if os.environ.get("TEST_NO_SERVER"):
        sys.exit(9)
    state.write_text(json.dumps([p for p in records if p["plugin_id"] != args[2]]))
elif args[:2] == ["plugin", "link"] and len(args) == 3:
    original = json.loads(os.environ["TEST_ORIGINAL"])
    records.extend(p for p in original if p.get("plugin_root") == args[2])
    state.write_text(json.dumps(records))
else:
    raise AssertionError("Unexpected Herdr command: " + repr(args))
'''

JJ = "NathanFlurry/herdr-plugin-jj-workspace"
PROJECTS = "eliasstravik/herdr-projects"


def legacy(plugin_id="nathanflurry.jj-workspace", enabled=True, root=None):
    suffix = ("herdr-plugin-jj-workspace-dir" if plugin_id == "nathanflurry.jj-workspace"
              else "herdr-projects-plugin-dir")
    return {"plugin_id": plugin_id, "enabled": enabled, "source": {"kind": "local"},
            "plugin_root": root or "/nix/store/" + "a" * 32 + "-" + suffix}


@unittest.skipUnless(os.environ.get("HERDR_PLUGINS_INSTALLER"),
                     "Set HERDR_PLUGINS_INSTALLER to the Nix-built installer")
class PluginInstallerTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="herdr-installer-test-")
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name)
        self.mock = self.home / "herdr"
        self.mock.write_text(f"#!{sys.executable}\n" + MOCK_HERDR)
        self.mock.chmod(0o755)
        self.state = self.home / "state.json"
        self.calls = self.home / "calls.jsonl"
        self.state.write_text("[]")
        self.env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin",
                    "TEST_STATE": str(self.state), "TEST_CALLS": str(self.calls)}

    def run_installer(self, *plugins, **env):
        self.env["TEST_ORIGINAL"] = self.state.read_text()
        return subprocess.run(
            [os.environ["HERDR_PLUGINS_INSTALLER"], str(self.mock), *plugins],
            env=self.env | env, input="not a consent response", text=True,
            capture_output=True, timeout=30,
        )

    def mutations(self):
        if not self.calls.exists():
            return []
        return [args for args in map(json.loads, self.calls.read_text().splitlines())
                if args != ["plugin", "list", "--json"]]

    def test_empty_list_does_nothing(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())

    def test_missing_plugins_install_noninteractively_and_only_once(self):
        for _ in range(2):
            result = self.run_installer(JJ, PROJECTS, JJ)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mutations(), [["plugin", "install", "--yes", JJ],
                                           ["plugin", "install", "--yes", PROJECTS]])

    def test_installed_disabled_plugin_is_not_updated_or_enabled(self):
        record = {"plugin_id": "herdr-projects", "enabled": False,
                  "source": {"kind": "github", "owner": "ELIASSTRAVIK",
                             "repo": "HERDR-PROJECTS", "resolved_commit": "user-version"}}
        self.state.write_text(json.dumps([record]))
        result = self.run_installer(PROJECTS)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.state.read_text()), [record])
        self.assertEqual(self.mutations(), [])

    def test_subdirectory_identity_is_preserved(self):
        result = self.run_installer("Owner/Repo/plugins/One", "owner/repo/plugins/One")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mutations(), [["plugin", "install", "--yes", "Owner/Repo/plugins/One"]])

    def test_known_enabled_nix_links_migrate_once(self):
        self.state.write_text(json.dumps([legacy(), legacy("herdr-projects")]))
        for _ in range(2):
            result = self.run_installer(JJ, PROJECTS)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.mutations(), [
            ["plugin", "unlink", "nathanflurry.jj-workspace"],
            ["plugin", "install", "--yes", JJ],
            ["plugin", "unlink", "herdr-projects"],
            ["plugin", "install", "--yes", PROJECTS],
        ])

    def test_disabled_legacy_link_is_not_reenabled_or_unlinked(self):
        record = legacy(enabled=False)
        self.state.write_text(json.dumps([record]))
        result = self.run_installer(JJ)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disabled legacy Nix link", result.stderr)
        self.assertEqual(self.mutations(), [])
        self.assertEqual(json.loads(self.state.read_text()), [record])

    def test_development_and_unknown_store_links_are_never_unlinked(self):
        for root in [str(self.home / "development"), "/nix/store/" + "b" * 32 + "-other-plugin"]:
            with self.subTest(root=root):
                self.calls.unlink(missing_ok=True)
                record = legacy(root=root)
                self.state.write_text(json.dumps([record]))
                result = self.run_installer(JJ)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.mutations(), [["plugin", "install", "--yes", JJ]])
                self.assertEqual(json.loads(self.state.read_text()), [record])

    def test_failed_migration_restores_old_link(self):
        record = legacy()
        self.state.write_text(json.dumps([record]))
        result = self.run_installer(JJ, TEST_FAIL_INSTALL="1")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.mutations(), [
            ["plugin", "unlink", "nathanflurry.jj-workspace"],
            ["plugin", "install", "--yes", JJ],
            ["plugin", "link", record["plugin_root"]],
        ])
        self.assertEqual(json.loads(self.state.read_text()), [record])

    def test_offline_legacy_migration_does_not_start_a_server(self):
        record = legacy()
        self.state.write_text(json.dumps([record]))
        result = self.run_installer(JJ, TEST_NO_SERVER="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.mutations(), [["plugin", "unlink", "nathanflurry.jj-workspace"]])
        self.assertEqual(json.loads(self.state.read_text()), [record])

    def test_list_errors_do_not_trigger_install(self):
        result = self.run_installer(JJ, TEST_BAD_LIST="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.mutations(), [])

    def test_install_failures_are_reported(self):
        result = self.run_installer(JJ, TEST_FAIL_INSTALL="1")
        self.assertEqual(result.returncode, 7)
        self.assertEqual(json.loads(self.state.read_text()), [])

    def test_invalid_sources_are_not_executed(self):
        result = self.run_installer("--help")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
