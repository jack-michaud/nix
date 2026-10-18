"""Check the built plugin without contacting a live Herdr server.

Run with HERDR_PROJECTS_PLUGIN_DIR=/nix/store/...-herdr-projects-plugin-dir
python3 -m unittest discover -s modules/shared/shells/herdr/tests -v
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest


@unittest.skipUnless(os.environ.get("HERDR_PROJECTS_PLUGIN_DIR"),
                     "Set HERDR_PROJECTS_PLUGIN_DIR to the built plugin directory")
class ProjectsPluginTest(unittest.TestCase):
    def setUp(self):
        self.plugin = Path(os.environ["HERDR_PROJECTS_PLUGIN_DIR"]).resolve()
        self.scratch = tempfile.TemporaryDirectory(prefix="herdr-projects-test-")
        self.addCleanup(self.scratch.cleanup)
        self.home = Path(self.scratch.name)
        stub = self.home / "herdr"
        stub.write_text(
            '#!/bin/sh\ncase "$1" in\n'
            '--version) echo "herdr 0.9.5";;\n'
            'plugin) printf "%s\\n" "$TEST_PLUGIN_JSON";;\n'
            '*) echo "{}";;\nesac\n'
        )
        stub.chmod(0o755)
        # Do not inherit credentials, board paths, agent sockets or real Herdr.
        self.env = {
            "HOME": str(self.home), "SHELL": "/bin/sh",
            "PATH": f"{self.home}/.herdr-projects/data/bin:/usr/bin:/bin",
            "HERDR_BIN_PATH": str(stub),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "HERDR_PROJECTS_HOME": str(self.home / ".herdr-projects"),
            "HERDR_PROJECTS_INLINE": "1",
            "HERDR_SOCKET_PATH": str(self.home / "absent.sock"),
        }
        self.register(self.plugin)

    def register(self, root):
        self.env["TEST_PLUGIN_JSON"] = json.dumps({"plugins": [{
            "plugin_id": "herdr-projects", "version": "1.2.2",
            "min_herdr_version": "0.9.3", "plugin_root": str(root),
            "enabled": True, "source": {"kind": "local"},
        }]})

    def run_plugin(self, *args):
        return subprocess.run(
            ["/bin/sh", str(self.plugin / "bin/run.sh"), *args],
            cwd=self.home, env=self.env, capture_output=True, text=True, timeout=45,
        )

    def test_manifest_and_dispatch(self):
        manifest = self.plugin / "herdr-plugin.toml"
        self.assertFalse(manifest.is_symlink())
        self.assertEqual(tomllib.loads(manifest.read_text())["id"], "herdr-projects")
        result = self.run_plugin("--fetch")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_plugin("version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("herdr-projects 1.2.2 (", result.stdout)

    def test_install_and_doctor_accept_same_canonical_program(self):
        result = self.run_plugin("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        program = self.plugin / "target/release/herdr-projects"
        self.assertTrue(program.is_file())
        self.assertTrue(os.access(program, os.X_OK))
        launcher = self.home / ".herdr-projects/data/bin/herdr-projects"
        self.assertIn(str(program.resolve()), launcher.read_text())
        result = self.run_plugin("doctor")
        self.assertNotIn("not the plugin's program", result.stdout)
        self.assertIn("✓ The launcher", result.stdout)
        self.assertIn("and a shell finds it on the PATH", result.stdout)
        # Other doctor areas intentionally see no configured agents/repos here.

    def test_doctor_detects_missing_layout_negative_control(self):
        result = self.run_plugin("install")
        self.assertEqual(result.returncode, 0, result.stderr)
        missing_layout = self.home / "plugin-without-program"
        missing_layout.mkdir()
        self.register(missing_layout)
        result = self.run_plugin("doctor")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not the plugin's program", result.stdout)


if __name__ == "__main__":
    unittest.main()
