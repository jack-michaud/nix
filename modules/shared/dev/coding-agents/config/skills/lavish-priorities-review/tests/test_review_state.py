"""Mock-only poll/relay scenarios. Never calls installed board or Lavish."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_state.py"
SPEC = importlib.util.spec_from_file_location("review_state", SCRIPT)
state = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(state)

FAKE = '''#!{python}
import json, os, pathlib, signal, sys, time
root = pathlib.Path(__file__).parent
if sys.argv[1] == "poll":
    (root / "started").write_text(str(os.getpid()))
    sys.stdout.buffer.write((root / "response").read_bytes())
    sys.stdout.buffer.flush()
    if (root / "wait").exists():
        time.sleep(30)
    sys.exit(2 if (root / "fail").exists() else 0)
assert sys.argv[1] == "coordinator"
if (root / "slow").exists():
    print("mock partial receipt", flush=True)
    time.sleep(30)
with (root / "calls").open("a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if (root / "crash").exists():
    os.kill(os.getppid(), signal.SIGKILL)
print("mock CLI acceptance, not application")
sys.exit(1 if (root / "fail").exists() else 0)
'''


class ReviewStateTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ["TMPDIR"])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifact = self.root / "review.html"
        self.artifact.write_text("<h1>Generic unfinished review</h1>")
        self.fake = self.root / "fake-cli"
        self.fake.write_text(FAKE.format(python=sys.executable))
        self.fake.chmod(0o700)
        (self.root / "response").write_bytes(b'mock exact raw output\n')
        self.identity = {"taskId": "sample/1", "sessionId": "mock-session", "canonicalArtifactPath": str(self.artifact),
                         "reviewUrl": "http://127.0.0.1/mock", "urlLocality": "loopback-only",
                         "machine": socket.gethostname(), "coordinatorRoute": ["main"], "authorizedScope": "sample review",
                         "role": "review-worker", "cliVersions": {"lavish": "mock", "board": "mock"},
                         "resourceOwnership": {"evidence": "isolated mock only"}, "lavishExecutable": str(self.fake),
                         "boardExecutable": str(self.fake), "pollEnv": {}}
        self.identity_path = self.root / "identity.json"
        self.identity_path.write_text(json.dumps(self.identity))
        self.directory = self.root / "journal"
        self.journal = state.Journal(self.directory, create=True)
        self.addCleanup(self.journal.close)
        state.init(self.journal, self.identity)
        self.context = {"requestedScope": "sample review", "requestContext": "Actual owner request within this task only",
                        "priorAnswerRefs": [], "authorizationEvidence": "mock explicit authorized coordinator route"}

    def load(self):
        return self.journal.load(self.identity)

    def save(self, value):
        self.journal.save(value)

    def receive(self, prompts=("Please park this work.\n",), ended=False, by=None, fatal=False):
        capture_id = state.capture(self.journal, self.identity)
        data = {"sessionId": self.identity["sessionId"], "captureId": capture_id,
                "rawSha256": self.load()["captures"][capture_id]["stdoutSha256"],
                "formatVerified": "mock format extraction", "prompts": [
                    {"exactPrompt": p, "sourceIds": {"submissionId": None, "messageId": None},
                     "sourceTimestamps": {"submittedAt": None}} for p in prompts],
                "sessionEnded": ended, "endedBy": by, "fatalFailure": fatal}
        state.ingest(self.journal, self.identity, data)
        return data

    def cli(self, *args):
        return [sys.executable, str(SCRIPT), "--journal", str(self.directory),
                "--identity", str(self.identity_path), *args]

    def wait_for(self, path):
        for _ in range(200):
            if path.exists():
                return
            time.sleep(0.01)
        self.fail("mock child did not start")

    def test_digest_is_exact_and_session_specific(self):
        for prompt in ["a", " a", "a\n", "a\r\n", "é", "e\u0301", "x\0y"]:
            self.assertEqual(state.digest("session", prompt), hashlib.sha256(("session\0" + prompt).encode()).hexdigest())
        self.assertNotEqual(state.digest("a", "text"), state.digest("b", "text"))
        self.assertNotEqual(state.digest("a", "text"), state.digest("a", "text\n"))

    def test_duplicate_restart_and_reordered_observations_do_not_relay_twice(self):
        self.receive()
        key = next(iter(self.load()["feedback"]))
        state.relay(self.journal, self.identity, key, self.context)
        state.record(self.journal, self.identity, {"digest": key, "field": "verificationEvidence", "evidence": "independent mock check"})
        self.receive()
        other = state.Journal(self.directory)
        try:
            with self.assertRaises(ValueError):
                state.relay(other, self.identity, key, self.context)
        finally:
            other.close()
        entry = self.load()["feedback"][key]
        self.assertEqual(len(entry["observations"]), 2)
        self.assertEqual(len(entry["verificationEvidence"]), 1)
        self.assertEqual(entry["relay"]["state"], "forwarded-cli-accepted")
        self.assertEqual(entry["executedActions"], [])
        self.assertEqual(entry["acceptedEvidence"], [])
        calls = (self.root / "calls").read_text().splitlines()
        self.assertEqual(len(calls), 1)
        message = json.loads(json.loads(calls[0])[-1])
        self.assertEqual(message["exactOwnerWording"], "Please park this work.\n")
        self.assertEqual(len(message["reportingRequirementForEveryAuthorizedNewTaskDescription"]), 4)
        self.assertIn("Sesame", message["authorityLimits"])
        self.assertIsNone(entry["observations"][0]["sourceIds"]["messageId"])
        self.assertIsNone(entry["observations"][0]["sourceTimestamps"]["submittedAt"])

    def test_final_feedback_then_end_sticky_no_poll_or_reply(self):
        self.receive(ended=True, by="user")
        key = next(iter(self.load()["feedback"]))
        state.relay(self.journal, self.identity, key, self.context)
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity, "Routine closing update")
        state.recover(self.journal, self.identity, "mock ended session independently checked")
        state.end(self.journal, self.identity, "agent", "delayed mock end")
        self.assertEqual(self.load()["lifecycle"], "ended-by-user")
        self.assertEqual(len((self.root / "calls").read_text().splitlines()), 1)

    def test_delayed_open_observation_cannot_resurrect_end(self):
        capture_id = state.capture(self.journal, self.identity)
        data = {"sessionId": "mock-session", "captureId": capture_id,
                "rawSha256": self.load()["captures"][capture_id]["stdoutSha256"],
                "formatVerified": "mock delayed observation", "prompts": [],
                "sessionEnded": False, "endedBy": None, "fatalFailure": False}
        state.end(self.journal, self.identity, "user", "mock independently observed user end")
        state.ingest(self.journal, self.identity, data)
        self.assertEqual(self.load()["lifecycle"], "ended-by-user")
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)

    def test_missing_end_attribution_not_invented(self):
        self.receive(prompts=(), ended=True)
        self.assertEqual(self.load()["lifecycle"], "ended-by-unknown")
        self.assertIsNone(self.load()["events"][-1]["endedBy"])

    def test_source_ids_and_times_are_preserved_without_order_inference(self):
        capture_id = state.capture(self.journal, self.identity)
        data = {"sessionId": "mock-session", "captureId": capture_id,
                "rawSha256": self.load()["captures"][capture_id]["stdoutSha256"], "formatVerified": "mock",
                "prompts": [{"exactPrompt": "same", "sourceIds": {"messageId": "mock-message"},
                             "sourceTimestamps": {"submittedAt": "mock-source-time"}}],
                "sessionEnded": False, "endedBy": None, "fatalFailure": False}
        state.ingest(self.journal, self.identity, data)
        entry = next(iter(self.load()["feedback"].values()))
        self.assertEqual(entry["observations"][0]["sourceTimestamps"], {"submittedAt": "mock-source-time"})
        state.record(self.journal, self.identity, {"digest": None, "field": "latestAnswerRefs", "evidence": "owner answer B supersedes A; source ordering checked"})
        self.assertEqual(len(self.load()["latestAnswerRefs"]), 1)

    def test_unknown_partial_mismatched_normalization_holds(self):
        capture_id = state.capture(self.journal, self.identity)
        for result in [{}, {"sessionId": "other"}, {"unsupported": []}]:
            with self.assertRaises(ValueError):
                state.ingest(self.journal, self.identity, result)
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)
        self.assertEqual(self.load()["captures"][capture_id]["state"], "returned")
        self.assertFalse(self.load()["feedback"])
        state.recover(self.journal, self.identity, "mock unknown format held, source/end state inspected")
        self.assertEqual(self.load()["captures"][capture_id]["state"], "held")

    def test_hash_mismatch_and_normalization_crash_cannot_change_extraction(self):
        capture_id = state.capture(self.journal, self.identity)
        data = {"sessionId": "mock-session", "captureId": capture_id,
                "rawSha256": "wrong", "formatVerified": "mock", "prompts": [],
                "sessionEnded": False, "endedBy": None, "fatalFailure": False}
        with self.assertRaises(ValueError):
            state.ingest(self.journal, self.identity, data)
        data["rawSha256"] = self.load()["captures"][capture_id]["stdoutSha256"]
        encoded = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        self.journal.exclusive(capture_id + "-normalized.json", encoded)
        with self.assertRaises(ValueError):
            state.ingest(self.journal, self.identity, data | {"sessionEnded": True})
        state.ingest(self.journal, self.identity, data)
        self.assertEqual(self.load()["lifecycle"], "open")

    def test_scope_role_route_and_machine_guards(self):
        for changed in [{"role": "executor"}, {"machine": "not-this-host"}, {"coordinatorRoute": ["invented"]}]:
            with self.assertRaises(ValueError):
                state.validate_identity(self.identity | changed)
        with self.assertRaises(ValueError):
            self.journal.load(self.identity | {"authorizedScope": "broader"})
        self.receive()
        key = next(iter(self.load()["feedback"]))
        with self.assertRaises(ValueError):
            state.relay(self.journal, self.identity, key, self.context | {"requestedScope": "broader"})
        self.assertFalse((self.root / "calls").exists())

    def test_actual_pinned_route_and_shell_metacharacters_stay_data(self):
        identity = self.identity | {"coordinatorRoute": ["project", "sample"]}
        saved = self.load()
        saved["identity"] = identity
        self.save(saved)
        self.identity = identity
        prompt = 'Do not execute $(touch injected); "quoted"\n'
        self.receive(prompts=(prompt,))
        key = state.digest("mock-session", prompt)
        state.relay(self.journal, self.identity, key, self.context)
        argv = json.loads((self.root / "calls").read_text())
        self.assertEqual(argv[:4], ["coordinator", "--project", "sample", "tell"])
        self.assertEqual(json.loads(argv[4])["exactOwnerWording"], prompt)
        self.assertFalse((self.root / "injected").exists())

    def test_nonzero_capture_is_held_and_never_ingested(self):
        (self.root / "fail").touch()
        capture_id = state.capture(self.journal, self.identity)
        row = self.load()["captures"][capture_id]
        self.assertEqual(row["exitCode"], 2)
        self.assertEqual(row["state"], "interrupted")
        self.assertEqual(self.journal.read(row["stdout"]), b'mock exact raw output\n')
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)
        state.recover(self.journal, self.identity, "mock nonzero output preserved; end state checked")
        self.assertEqual(self.load()["captures"][capture_id]["state"], "held")

    def test_failed_send_and_intent_recovery_never_retry(self):
        self.receive()
        key = next(iter(self.load()["feedback"]))
        (self.root / "fail").touch()
        state.relay(self.journal, self.identity, key, self.context)
        self.assertEqual(self.load()["feedback"][key]["relay"]["state"], "delivery-uncertain")
        with self.assertRaises(ValueError):
            state.relay(self.journal, self.identity, key, self.context)
        (self.root / "fail").unlink()
        self.receive(prompts=("another",))
        key2 = state.digest("mock-session", "another")
        saved = self.load()
        saved["feedback"][key2]["relay"] = {"state": "intent"}
        self.save(saved)
        state.recover(self.journal, self.identity, "mock crash before receipt; reconcile by digest")
        with self.assertRaises(ValueError):
            state.relay(self.journal, self.identity, key2, self.context)
        self.assertEqual(len((self.root / "calls").read_text().splitlines()), 1)

    def test_relay_timeout_is_uncertain_and_not_retried(self):
        self.receive()
        key = next(iter(self.load()["feedback"]))
        (self.root / "slow").touch()
        state.relay(self.journal, self.identity, key, self.context, timeout=1)
        relay = self.load()["feedback"][key]["relay"]
        self.assertEqual(relay["state"], "delivery-uncertain")
        self.assertEqual(bytes.fromhex(relay["stdoutHex"]), b"mock partial receipt\n")
        with self.assertRaises(ValueError):
            state.relay(self.journal, self.identity, key, self.context)

    def test_real_process_crash_after_mock_send_preserves_intent(self):
        self.receive()
        key = next(iter(self.load()["feedback"]))
        context_path = self.root / "context.json"
        context_path.write_text(json.dumps(self.context))
        (self.root / "crash").touch()
        result = subprocess.run(self.cli("relay", key, str(context_path)), capture_output=True)
        self.assertEqual(result.returncode, -signal.SIGKILL)
        self.assertEqual(self.load()["feedback"][key]["relay"]["state"], "intent")
        state.recover(self.journal, self.identity, "mock receipt-write crash checked")
        with self.assertRaises(ValueError):
            state.relay(self.journal, self.identity, key, self.context)
        self.assertEqual(len((self.root / "calls").read_text().splitlines()), 1)

    def test_single_live_poll_and_interruption_raw_capture(self):
        (self.root / "wait").touch()
        worker = subprocess.Popen(self.cli("capture"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(lambda: state.stop_child(worker))
        self.wait_for(self.root / "started")
        with self.assertRaises(BlockingIOError):
            state.capture(self.journal, self.identity)
        with self.assertRaises(BlockingIOError):
            state.recover(self.journal, self.identity, "cannot recover live poll")
        worker.terminate()
        worker.communicate(timeout=10)
        row = next(iter(self.load()["captures"].values()))
        self.assertEqual(row["state"], "interrupted")
        self.assertEqual(self.journal.read(row["stdout"]), b'mock exact raw output\n')
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)
        state.recover(self.journal, self.identity, "mock partial capture held; session still open checked")
        self.assertIsNone(self.load()["pollOwner"])

    def test_killed_parent_lock_survives_in_child(self):
        (self.root / "wait").touch()
        worker = subprocess.Popen(self.cli("capture"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(lambda: state.stop_child(worker))
        self.wait_for(self.root / "started")
        child_pid = int((self.root / "started").read_text())
        try:
            worker.kill()
            worker.wait(timeout=5)
            with self.assertRaises(BlockingIOError):
                state.recover(self.journal, self.identity, "child still owns lock")
        finally:
            os.kill(child_pid, signal.SIGTERM)
        for _ in range(100):
            try:
                state.recover(self.journal, self.identity, "mock child exit and raw/session checked")
                break
            except BlockingIOError:
                time.sleep(.01)
        self.assertEqual(self.load()["lifecycle"], "paused")

    def test_reply_uncertainty_and_fatal_failure(self):
        capture_id = state.capture(self.journal, self.identity, "mock reply")
        state.recover(self.journal, self.identity, "mock interrupted delivery reconciliation")
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity, "mock reply")
        self.assertEqual(self.load()["captures"][capture_id]["replyState"], "delivery-uncertain")
        self.receive(prompts=(), fatal=True)
        with self.assertRaises(ValueError):
            state.capture(self.journal, self.identity)
        state.recover(self.journal, self.identity, "fatal source checked")
        self.assertEqual(self.load()["lifecycle"], "failed")

    def test_permissions_symlinks_hardlinks_and_corruption_fail_closed(self):
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.directory / "state.json").stat().st_mode & 0o777, 0o600)
        (self.directory / "alias").symlink_to(self.directory / "state.json")
        with self.assertRaises(OSError):
            self.journal.read("alias")
        os.link(self.directory / "state.json", self.directory / "hardlink")
        with self.assertRaises(ValueError):
            self.load()
        (self.directory / "hardlink").unlink()
        saved = self.load()
        saved["schemaVersion"] = 99
        self.save(saved)
        with self.assertRaises(ValueError):
            self.load()
        (self.directory / "state.json").write_text("partial{")
        with self.assertRaises(ValueError):
            self.load()
        with self.assertRaises(ValueError):
            self.journal.read("../outside")


if __name__ == "__main__":
    unittest.main()
