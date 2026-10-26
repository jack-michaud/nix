"""Synthetic proof tests, not evidence that any live activation is bounded."""
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("gate", ROOT / "config/agent_config_gate.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


def proof(path=".agents/rules/routing.md", kind="agent-instructions"):
    return {"schema": 1, "target": gate.TARGET.copy(),
            "source": {"origin": gate.ORIGIN, "base": "a" * 40, "head": "b" * 40,
                       "clean": True, "pendingChanges": [], "paths": ["modules/shared/shells/herdr/projects.nix"]},
            "gates": {"head": "b" * 40, "sourceApproved": True, "independentReview": True,
                      "requiredChecks": True, "exactSource": True},
            "effects": {"head": "b" * 40, "target": gate.TARGET.copy(), "complete": True,
                        "baselineHash": "c" * 64, "outputHash": "d" * 64,
                        "files": [{"path": path, "kind": kind, "before": None, "after": "e" * 64}],
                        "activationActions": [{"kind": "install-file", "path": path}],
                        "packages": [], "services": [], "credentials": [], "restarts": [], "unknown": []},
            "event": {"identity": gate.IDENTITY, "kind": "merged", "repo": "dotfiles", "head": "b" * 40, "origin": "source-merge"},
            "applicationState": "not-started"}


class GateTest(unittest.TestCase):
    def test_three_ai_only_synthetic_examples_validate_but_are_not_attestations(self):
        for path, kind in [(".agents/AGENTS.md", "agent-instructions"),
                           (".pi/agent/skills/herdr-orchestration/SKILL.md", "agent-skill"),
                           (".config/herdr-projects-nix/declarations.json", "projects-declarations")]:
            with self.subTest(path=path):
                self.assertEqual(gate.assess(proof(path, kind)), [])

    def test_mixed_source_and_misleading_safe_source_with_broad_effects(self):
        mixed = proof()
        mixed["source"]["paths"].append("hosts/aarch64-darwin/DAMOCLES/default.nix")
        self.assertTrue(gate.assess(mixed))
        for category in ("packages", "services", "credentials", "restarts", "unknown"):
            broader = proof()
            broader["effects"][category] = ["unrelated"]
            self.assertTrue(gate.assess(broader))
        self.assertTrue(gate.assess(proof(".ssh/config", "agent-instructions")))
        self.assertTrue(gate.assess(proof(".prime/agent/skills/herdr-orchestration/SKILL.md", "agent-skill")))
        bad = proof()
        bad["effects"]["activationActions"].append({"kind": "run-command", "command": "darwin-rebuild switch"})
        self.assertTrue(gate.assess(bad))

    def test_unknown_incomplete_dirty_pending_or_mismatched_evidence(self):
        variants = [("source", "clean", False), ("source", "pendingChanges", ["unrelated"]),
                    ("source", "paths", []), ("effects", "complete", False), ("effects", "head", "f" * 40),
                    ("effects", "target", {"machine": "Spark"}), ("effects", "outputHash", None)]
        for section, key, value in variants:
            candidate = proof()
            candidate[section][key] = value
            self.assertTrue(gate.assess(candidate), (section, key))
        for section in ("source", "gates", "effects", "event"):
            candidate = proof()
            candidate[section]["unknown"] = "extra"
            self.assertTrue(gate.assess(candidate))
        for key in gate.TARGET:
            candidate = proof()
            candidate["target"][key] = "wrong"
            self.assertTrue(gate.assess(candidate))

    def test_each_approval_review_check_gate_required_and_exact(self):
        for key in ("sourceApproved", "independentReview", "requiredChecks", "exactSource"):
            for missing in (False, True):
                candidate = proof()
                if missing:
                    del candidate["gates"][key]
                else:
                    candidate["gates"][key] = False
                self.assertTrue(gate.assess(candidate))
        candidate = proof()
        candidate["gates"]["head"] = "f" * 40
        self.assertTrue(gate.assess(candidate))

    def test_recursive_reordered_and_uncertain_attempts_refused(self):
        for key, value in (("origin", "agent-config-gate"), ("head", "a" * 40), ("repo", "other"), ("kind", "done")):
            candidate = proof()
            candidate["event"][key] = value
            self.assertTrue(gate.assess(candidate))
        for value in ("in-flight", "uncertain", "completed", "failed"):
            candidate = proof()
            candidate["applicationState"] = value
            self.assertTrue(gate.assess(candidate))

    def test_no_shell_or_path_injection(self):
        for path in ("../../.ssh/config", "/etc/passwd", ".agents/../.ssh/config", ".pi//agent/skills/x", "$(touch pwned)"):
            self.assertTrue(gate.assess(proof(path, "agent-skill")))
        candidate = proof()
        candidate["source"]["head"] = "HEAD; touch pwned"
        self.assertTrue(gate.assess(candidate))

    def test_malformed_candidates_refused(self):
        for value in (None, [], {}, {"schema": 1}):
            self.assertTrue(gate.assess(value))
        for section in ("source", "effects", "gates", "event"):
            candidate = proof()
            candidate[section] = []
            self.assertTrue(gate.assess(candidate))

    def test_receipts_are_immutable_private_idempotent_and_target_single_flight(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state"
            receipt = {"target": gate.TARGET, "source": "b" * 40, "status": "blocked-not-activated"}
            path = gate.store_receipt(state, receipt)
            before = path.stat().st_mtime_ns
            self.assertEqual(path, gate.store_receipt(state, copy.deepcopy(receipt)))
            self.assertEqual(before, path.stat().st_mtime_ns)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with (state / "owner.lock").open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaises(ValueError):
                    gate.store_receipt(state, receipt)
            self.assertTrue(path.exists())
            self.assertTrue((state / "owner.lock").exists())

    def test_independent_git_checks_complete_source_dirty_and_ordering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def run(*args):
                return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
            run("init", "-q")
            run("config", "user.email", "fixture@example.invalid")
            run("config", "user.name", "Fixture")
            run("remote", "add", "origin", gate.ORIGIN)
            file = root / "modules/shared/shells/herdr/_projects.nix"
            file.parent.mkdir(parents=True)
            file.write_text("baseline")
            run("add", ".")
            run("commit", "-qm", "baseline")
            base = run("rev-parse", "HEAD")
            file.write_text("candidate")
            run("commit", "-qam", "candidate")
            head = run("rev-parse", "HEAD")
            run("update-ref", "refs/remotes/origin/main", head)
            candidate = proof()
            candidate["source"].update(base=base, head=head, paths=[str(file.relative_to(root))])
            with patch.object(gate, "CHECKOUT", str(root.resolve())):
                self.assertEqual(gate.source_check(root, candidate), [])
                candidate["source"]["paths"] = ["modules/shared/shells/herdr/omitted.nix"]
                self.assertTrue(gate.source_check(root, candidate))
                candidate["source"]["paths"] = [str(file.relative_to(root))]
                (root / "unrelated").write_text("pending")
                self.assertTrue(gate.source_check(root, candidate))
                (root / "unrelated").unlink()
                candidate["source"]["head"] = base
                self.assertTrue(gate.source_check(root, candidate))
                self.assertEqual(run("rev-parse", "HEAD"), head)

    def test_live_entrypoint_never_treats_supplied_proof_as_approval_or_executes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "proof.json"
            source.write_text(json.dumps(proof()))
            sentinel = root / "mutable-state"
            sentinel.write_text("runtime work")
            command = [sys.executable, str(ROOT / "config/agent_config_gate.py"), "check", "--proof", str(source),
                       "--repository", str(root), "--receipts", str(root / "receipts")]
            first = subprocess.run(command, text=True, capture_output=True, timeout=10)
            second = subprocess.run(command, text=True, capture_output=True, timeout=10)
            self.assertEqual(first.returncode, 1, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertIn("blocked-not-activated", first.stdout)
            self.assertEqual(sentinel.read_text(), "runtime work")
            self.assertEqual(len(list((root / "receipts").glob("*.json"))), 1)
            self.assertFalse((root / "pwned").exists())


if __name__ == "__main__":
    unittest.main()
