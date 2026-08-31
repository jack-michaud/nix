"""Unit tests for the portable rule parser and glob seam."""

import unittest

from agent_rules import glob_to_regexp, parse_rule, parse_paths_list


class AgentRulesTest(unittest.TestCase):
    def test_frontmatter_spellings_and_always_on(self):
        self.assertEqual(parse_paths_list('paths: ["src/**", \'lib/*.py\']'), ["src/**", "lib/*.py"])
        self.assertEqual(parse_paths_list("paths:\n  - 'src/**'\n  - lib/*.py\n"), ["src/**", "lib/*.py"])
        self.assertEqual(parse_rule("plain.md", "hello\n")["paths"], [])
        self.assertEqual(parse_rule("scoped.md", "---\npaths: [src/**]\n---\nbody")["body"], "body")

    def test_glob_anchors_and_metacharacters(self):
        self.assertTrue(glob_to_regexp("/tmp/src/**").match("/tmp/src/a/b.py"))
        self.assertTrue(glob_to_regexp("/tmp/src/*.py").match("/tmp/src/a.py"))
        self.assertFalse(glob_to_regexp("/tmp/src/*.py").match("/tmp/src/a/b.py"))
        self.assertTrue(glob_to_regexp("/tmp/a[1].py").match("/tmp/a[1].py"))
        self.assertFalse(glob_to_regexp("/tmp/a[1].py").match("/tmp/a1.py"))


if __name__ == "__main__":
    unittest.main()
