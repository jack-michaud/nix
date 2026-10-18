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
BASE_PACKAGES = [pin.rsplit("@", 1)[0] for pin in PINS]
LOCAL = "../../Code/github.com/kylesnowschwartz/pi-bionic-reading"


def merge(settings, packages=PINS):
    result = subprocess.run(
        ["jq", "--argjson", "packages", json.dumps([packages]),
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

    def test_slashed_git_refs_are_repinned(self):
        for index in [0, 2, 3]:
            pin = PINS[index]
            repository = pin.rsplit("@", 1)[0]
            for ref in ["feature/review", "refs/tags/v1.0", "team/feature/review"]:
                for filtered in [False, True]:
                    with self.subTest(pin=pin, ref=ref, filtered=filtered):
                        source = repository + "@" + ref
                        entry = {"source": source, "extensions": []} if filtered else source
                        result = merge({"packages": [entry, pin]})
                        expected = {"source": pin, "extensions": []} if filtered else pin
                        self.assertEqual(len(result["packages"]), len(PINS))
                        self.assertIn(expected, result["packages"])
                        self.assertEqual(merge(result), result)

    def test_slashed_refs_in_all_verified_github_forms(self):
        for source in ["git:github.com/jack-michaud/pi-nvim@feature/review",
                       "git:git@github.com:jack-michaud/pi-nvim.git@feature/review",
                       "git:ssh://git@github.com/jack-michaud/pi-nvim.git@refs/tags/v1",
                       "https://github.com/jack-michaud/pi-nvim.git@feature/review"]:
            with self.subTest(source=source):
                result = merge({"packages": [{"source": source, "extensions": []}]})
                self.assertEqual(len(result["packages"]), len(PINS))
                self.assertIn({"source": PINS[2], "extensions": []}, result["packages"])

    def test_unrelated_ssh_sources_keep_their_identity(self):
        others = ["git:git@gitlab.com:algal/pi-openai-server-compaction@feature/review",
                  "git:git@github.com:algal/pi-openai-server-compaction-extra@feature/review"]
        result = merge({"packages": others})
        self.assertEqual(result["packages"], others + PINS)

    def test_unpinned_base_set_migrates_old_pins_and_local_sources(self):
        filtered = {"source": PINS[1], "extensions": [], "autoload": False}
        settings = {"theme": "dark", "skills": ["-../example"], "packages": [
            PINS[0], filtered, PINS[2].rsplit("@", 1)[0] + "@feature/review",
            LOCAL, "./unmanaged", *PINS,
        ]}
        result = merge(settings, BASE_PACKAGES)
        expected = ["./unmanaged", BASE_PACKAGES[0],
                    filtered | {"source": BASE_PACKAGES[1]}, *BASE_PACKAGES[2:]]
        self.assertEqual(result, settings | {"packages": expected})
        self.assertEqual(merge(result, BASE_PACKAGES), result)

    def test_unpinned_base_set_is_added_to_empty_settings(self):
        result = merge({}, BASE_PACKAGES)
        self.assertEqual(result, {"packages": BASE_PACKAGES})
        self.assertEqual(merge(result, BASE_PACKAGES), result)

    def test_unpinned_base_set_preserves_all_disabled_resources(self):
        for pin, source in zip(PINS, BASE_PACKAGES):
            with self.subTest(source=source):
                entry = {"source": pin, "extensions": [], "skills": [],
                         "prompts": [], "themes": [], "autoload": False}
                result = merge({"packages": [entry]}, BASE_PACKAGES)
                self.assertEqual(len(result["packages"]), len(BASE_PACKAGES))
                self.assertIn(entry | {"source": source}, result["packages"])

    def test_unversioned_npm_and_missing_packages(self):
        self.assertEqual(merge({"packages": ["npm:@langchain/langsmith-pi-extension"]}),
                         {"packages": PINS})
        self.assertEqual(merge({"packages": None}), {"packages": PINS})


if __name__ == "__main__":
    unittest.main()
