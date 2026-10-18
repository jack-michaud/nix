"""Exercise the exact jq filter used by Home Manager, without user state."""
import json
from pathlib import Path
import subprocess
import unittest

FILTER = Path(__file__).resolve().parents[1] / "merge-pi-packages.jq"
PINS = [
    "git:github.com/algal/pi-openai-server-compaction@reviewed",
    "npm:@langchain/langsmith-pi-extension@0.2.1",
    "git:git@github.com:jack-michaud/pi-nvim.git@reviewed",
    "git:github.com/kylesnowschwartz/pi-bionic-reading@reviewed",
]
LOCAL = "../../Code/github.com/kylesnowschwartz/pi-bionic-reading"


def merge(settings):
    result = subprocess.run(
        ["jq", "--argjson", "packages", json.dumps([PINS]),
         "--argjson", "aliases", json.dumps({LOCAL: PINS[3]}), "-f", str(FILTER)],
        input=json.dumps(settings), text=True, capture_output=True, check=True,
    )
    return json.loads(result.stdout)


class PiPackagesTest(unittest.TestCase):
    def test_empty_and_idempotent(self):
        result = merge({})
        self.assertEqual(result, {"packages": PINS})
        self.assertEqual(merge(result), result)

    def test_keeps_unrelated_settings_and_packages(self):
        other = ["git:github.com/algal/pi-openai-server-compaction-extra@dev",
                 "npm:@langchain/langsmith-pi-extension-extra@1",
                 "./private-local-extension", {"source": "npm:unmanaged", "skills": []}]
        settings = {"theme": "dark", "extensions": ["-builtin:mcp"],
                    "skills": ["-../skills/example"], "packages": other}
        result = merge(settings)
        self.assertEqual(result, settings | {"packages": other + PINS})

    def test_repins_without_enabling_filtered_resources(self):
        entry = {"source": "npm:@langchain/langsmith-pi-extension@0.1.0",
                 "extensions": [], "skills": [], "autoload": False}
        result = merge({"packages": [entry]})
        self.assertIn(entry | {"source": PINS[1]}, result["packages"])

    def test_adopts_local_path_and_keeps_object_over_duplicate_string(self):
        entry = {"source": LOCAL, "extensions": ["!index.ts"], "themes": []}
        result = merge({"packages": [PINS[3], entry]})
        self.assertEqual(len(result["packages"]), len(PINS))
        self.assertIn(entry | {"source": PINS[3]}, result["packages"])
        self.assertEqual(merge(result), result)

    def test_verified_github_source_forms(self):
        for source in ["git:github.com/jack-michaud/pi-nvim@old",
                       "git:git@github.com:jack-michaud/pi-nvim.git",
                       "git:ssh://git@github.com/jack-michaud/pi-nvim.git@old",
                       "https://github.com/jack-michaud/pi-nvim.git"]:
            with self.subTest(source=source):
                result = merge({"packages": [{"source": source, "extensions": []}]})
                self.assertEqual(len(result["packages"]), len(PINS))
                self.assertIn({"source": PINS[2], "extensions": []}, result["packages"])

    def test_unversioned_npm_and_missing_packages(self):
        self.assertEqual(merge({"packages": ["npm:@langchain/langsmith-pi-extension"]}),
                         {"packages": PINS})
        self.assertEqual(merge({"packages": None}), {"packages": PINS})


if __name__ == "__main__":
    unittest.main()
