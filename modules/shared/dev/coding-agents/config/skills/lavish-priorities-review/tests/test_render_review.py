"""Generator tests are offline; no synthetic owner feedback."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_review.py"
SPEC = importlib.util.spec_from_file_location("render_review", SCRIPT)
render = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(render)


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_sections_determinism_and_no_network_or_submission_controls(self):
        result = render.render("Priority review", "Requested area")
        self.assertEqual(result, render.render("Priority review", "Requested area"))
        for section in ("What moved forward", "A short priority sequence", "Current verified status",
                        "Next owner needs", "Explicitly parked", "Conditional dependencies",
                        "What remains uncertain", "Evidence and prior answers", "Review together"):
            self.assertIn(section, result)
        self.assertIn("Unfinished scaffold", result)
        self.assertIn('prefers-color-scheme:dark', result)
        self.assertIn('name="viewport"', result)
        for forbidden in ("<script", "<form", "queuePrompt(", "sendQueuedPrompts(", "https://", "http://",
                          "<iframe", "<link", "<img"):
            self.assertNotIn(forbidden, result)

    def test_escape_and_no_recursive_placeholder_substitution(self):
        result = render.render('<script>"&{{SCOPE}}', "<img onerror='x'>{{TITLE}}")
        self.assertIn('&lt;script&gt;&quot;&amp;{{SCOPE}}', result)
        self.assertIn("&lt;img onerror=&#x27;x&#x27;&gt;{{TITLE}}", result)
        self.assertNotIn("<script>", result)
        self.assertNotIn("<img ", result)

    def test_private_creation_and_no_overwrite(self):
        output = self.root / "report.html"
        render.create(output, "Title", "Scope")
        before = output.read_bytes()
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        with self.assertRaises(FileExistsError):
            render.create(output, "Changed", "Other scope")
        self.assertEqual(output.read_bytes(), before)

    def test_symlinks_dangling_links_and_parent_refused(self):
        target = self.root / "other-report"
        target.write_text("untouched")
        link = self.root / "link"
        link.symlink_to(target)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "missing")
        for path in (link, dangling):
            with self.assertRaises(OSError):
                render.create(path, "Title", "Scope")
        self.assertEqual(target.read_text(), "untouched")
        parent = self.root / "linked-dir"
        parent.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            render.create(parent / "new", "Title", "Scope")
        self.assertFalse((self.root / "new").exists())

    def test_unowned_effects_writable_parent_rejected(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            render.create(self.root / "new", "Title", "Scope")
        self.root.chmod(0o700)
        self.assertFalse((self.root / "new").exists())


if __name__ == "__main__":
    unittest.main()
