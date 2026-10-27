#!/usr/bin/env python3
"""Private foreground review journal. No daemon, wire-format parser or work executor."""
import argparse
import contextlib
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import stat
import subprocess
import sys
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(session, prompt):
    return sha((session + "\0" + prompt).encode("utf-8"))


def require(ok, message):
    if not ok:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value) and "\0" not in value


def read_json(path):
    return json.loads(Path(path).read_bytes())


def validate_identity(identity):
    required = {"taskId", "sessionId", "canonicalArtifactPath", "reviewUrl", "urlLocality",
                "machine", "coordinatorRoute", "authorizedScope", "role", "cliVersions",
                "resourceOwnership", "lavishExecutable", "boardExecutable", "pollEnv"}
    require(isinstance(identity, dict) and set(identity) == required, "unknown/incomplete identity")
    for key in required - {"coordinatorRoute", "cliVersions", "resourceOwnership", "pollEnv"}:
        require(nonempty(identity[key]), "invalid identity: " + key)
    require(identity["role"] == "review-worker", "helper is only for a review-worker")
    require(identity["machine"] == socket.gethostname(), "wrong poll machine")
    route = identity["coordinatorRoute"]
    require(route in (["main"], ["machine"]) or
            (isinstance(route, list) and len(route) == 2 and route[0] == "project" and nonempty(route[1])),
            "unsupported coordinator route")
    for key in ("canonicalArtifactPath", "lavishExecutable", "boardExecutable"):
        require(Path(identity[key]).is_absolute(), key + " must be absolute")
    require(Path(identity["canonicalArtifactPath"]).is_file(), "artifact must exist")
    require(not Path(identity["canonicalArtifactPath"]).is_symlink(), "artifact is a symlink")
    require(isinstance(identity["pollEnv"], dict) and
            set(identity["pollEnv"]) <= {"LAVISH_AXI_STATE_DIR", "LAVISH_AXI_PORT", "LAVISH_AXI_HOST"} and
            all(nonempty(v) for v in identity["pollEnv"].values()), "unsupported poll environment")
    require(isinstance(identity["cliVersions"], dict) and identity["cliVersions"] and
            isinstance(identity["resourceOwnership"], dict), "missing version/ownership record")


class Journal:
    def __init__(self, root, create=False):
        root = Path(root).absolute()
        if create:
            root.mkdir(mode=0o700)
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        info = os.fstat(self.fd)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            os.close(self.fd)
            raise ValueError("journal directory must be owned by you, mode 0700")

    def close(self):
        os.close(self.fd)

    def open(self, name, flags):
        require(Path(name).name == name and name not in (".", ".."), "unsafe journal filename")
        fd = os.open(name, flags | os.O_NOFOLLOW, 0o600, dir_fd=self.fd)
        info = os.fstat(fd)
        if not (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and
                stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1):
            os.close(fd)
            raise ValueError("unsafe journal file: " + name)
        return fd

    @contextlib.contextmanager
    def lock(self, name="state.lock"):
        fd = self.open(name, os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield fd
        finally:
            os.close(fd)

    def read(self, name):
        with os.fdopen(self.open(name, os.O_RDONLY), "rb") as handle:
            return handle.read()

    def exclusive(self, name, data):
        with os.fdopen(self.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(self.fd)

    def save(self, state):
        data = json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        name = "state-" + uuid.uuid4().hex + ".tmp"
        self.exclusive(name, data)
        os.replace(name, "state.json", src_dir_fd=self.fd, dst_dir_fd=self.fd)
        os.fsync(self.fd)

    def load(self, identity):
        state = json.loads(self.read("state.json"))
        require(state["schemaVersion"] == 1, "unknown journal schema")
        require(state["identity"] == identity, "identity/scope/route changed")
        require(state["lifecycle"] in {"open", "paused", "polling", "failed", "ended-by-user", "ended-by-agent", "ended-by-unknown"},
                "invalid lifecycle")
        require(isinstance(state["feedback"], dict) and isinstance(state["captures"], dict), "corrupt state")
        for key, entry in state["feedback"].items():
            require(key == digest(identity["sessionId"], entry["exactPrompt"]), "feedback digest mismatch")
            require(entry["relay"]["state"] in {"submitted", "intent", "delivery-uncertain", "forwarded-cli-accepted"},
                    "invalid relay state")
        return state


def init(journal, identity):
    validate_identity(identity)
    with journal.lock():
        journal.exclusive("state.json", (json.dumps({
            "schemaVersion": 1, "identity": identity, "lifecycle": "open", "pollOwner": None,
            "captures": {}, "feedback": {}, "events": [], "latestAnswerRefs": [],
            "checkInBaseline": None, "artifactRevisionHash": None,
        }, indent=2) + "\n").encode())


def stop_child(child):
    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def interrupted(signum, frame):
    raise InterruptedError("foreground capture interrupted by signal " + str(signum))


def capture(journal, identity, reply=None):
    with journal.lock("poll.lock") as poll_fd:
        with journal.lock():
            state = journal.load(identity)
            require(state["lifecycle"] in {"open", "paused"}, "review not open; recover interrupted poll first")
            require(all(c["state"] in {"ingested", "held"} for c in state["captures"].values()),
                    "unprocessed capture: ingest or recover with evidence first")
            if reply is not None:
                require(nonempty(reply), "empty reply")
                reply_hash = sha(reply.encode())
                require(not any(c.get("replyHash") == reply_hash for c in state["captures"].values()),
                        "reply already attempted; reconcile rather than repeat")
            capture_id = uuid.uuid4().hex
            row = {"state": "running", "startedAtLocal": now(), "stdout": capture_id + ".stdout",
                   "stderr": capture_id + ".stderr", "replyHash": sha(reply.encode()) if reply else None,
                   "reply": reply, "replyState": "delivery-uncertain" if reply else None}
            state["captures"][capture_id] = row
            state["lifecycle"] = "polling"
            state["pollOwner"] = {"pid": os.getpid(), "token": capture_id,
                                  "machine": identity["machine"], "taskId": identity["taskId"]}
            journal.save(state)
        child = None
        error = None
        code = None
        old_handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            with os.fdopen(journal.open(row["stdout"], os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as out, \
                    os.fdopen(journal.open(row["stderr"], os.O_WRONLY | os.O_CREAT | os.O_EXCL), "wb") as err:
                argv = [identity["lavishExecutable"], "poll", identity["canonicalArtifactPath"]]
                if reply is not None:
                    argv += ["--agent-reply", reply]
                child = subprocess.Popen(argv, stdout=out, stderr=err, pass_fds=(poll_fd,),
                                         env=os.environ | identity["pollEnv"])
                try:
                    code = child.wait()
                finally:
                    stop_child(child)
                    out.flush()
                    err.flush()
                    os.fsync(out.fileno())
                    os.fsync(err.fileno())
        except BaseException as exc:
            error = type(exc).__name__ + ": " + str(exc)
        finally:
            stop_child(child)
            for sig, handler in old_handlers.items():
                signal.signal(sig, handler)
            with journal.lock():
                state = journal.load(identity)
                row = state["captures"][capture_id]
                row.update(state="returned" if code == 0 and error is None else "interrupted",
                           exitCode=code, error=error, finishedAtLocal=now())
                for stream in ("stdout", "stderr"):
                    try:
                        row[stream + "Sha256"] = sha(journal.read(row[stream]))
                    except FileNotFoundError:
                        row[stream + "Sha256"] = None
                state["pollOwner"] = None
                state["lifecycle"] = "paused"
                journal.save(state)
        return capture_id


def ingest(journal, identity, result):
    required = {"sessionId", "captureId", "rawSha256", "formatVerified", "prompts",
                "sessionEnded", "endedBy", "fatalFailure"}
    require(isinstance(result, dict) and set(result) == required, "unknown/incomplete normalized result")
    require(result["sessionId"] == identity["sessionId"] and nonempty(result["formatVerified"]),
            "wrong session or unverified format")
    require(type(result["sessionEnded"]) is bool and type(result["fatalFailure"]) is bool,
            "invalid end/failure fields")
    require(result["endedBy"] in (None, "user", "agent") and
            (result["sessionEnded"] or result["endedBy"] is None), "invalid end attribution")
    require(isinstance(result["prompts"], list), "unsupported prompts")
    for prompt in result["prompts"]:
        require(isinstance(prompt, dict) and set(prompt) == {"exactPrompt", "sourceIds", "sourceTimestamps"}
                and isinstance(prompt["exactPrompt"], str), "unknown prompt shape")
        for field in ("sourceIds", "sourceTimestamps"):
            require(isinstance(prompt[field], dict) and
                    all(v is None or isinstance(v, str) for v in prompt[field].values()), "invalid source provenance")
    with journal.lock():
        state = journal.load(identity)
        require(state["lifecycle"] != "polling", "cannot ingest while polling")
        row = state["captures"][result["captureId"]]
        require(row["state"] == "returned", "capture incomplete or already processed")
        require(result["rawSha256"] == row["stdoutSha256"] == sha(journal.read(row["stdout"])),
                "raw capture hash mismatch")
        name = result["captureId"] + "-normalized.json"
        encoded = json.dumps(result, ensure_ascii=False, sort_keys=True).encode()
        try:
            journal.exclusive(name, encoded)
        except FileExistsError:
            require(journal.read(name) == encoded, "normalization changed after crash; hold for reconciliation")
        for prompt in result["prompts"]:
            key = digest(identity["sessionId"], prompt["exactPrompt"])
            observation = {"captureId": result["captureId"], "rawPollSha256": result["rawSha256"],
                           "sourceIds": prompt["sourceIds"], "sourceTimestamps": prompt["sourceTimestamps"],
                           "locallyObservedAt": now()}
            if key not in state["feedback"]:
                state["feedback"][key] = {"exactPrompt": prompt["exactPrompt"], "observations": [],
                    "relay": {"state": "submitted"}, "acceptedEvidence": [], "appliedEvidence": [],
                    "verificationEvidence": [], "executedActions": [], "artifactRevision": [], "replyState": []}
            state["feedback"][key]["observations"].append(observation)
        row["state"] = "ingested"
        row["replyState"] = "poll-returned-not-proof-of-reading" if row["reply"] else None
        if not state["lifecycle"].startswith("ended-"):
            state["lifecycle"] = ("ended-by-" + (result["endedBy"] or "unknown") if result["sessionEnded"]
                                  else "failed" if result["fatalFailure"] or state["lifecycle"] == "failed" else "open")
        state["events"].append({"type": "ingested", "captureId": result["captureId"],
                                "sessionEnded": result["sessionEnded"], "endedBy": result["endedBy"],
                                "atLocal": now()})
        journal.save(state)


def envelope(identity, key, entry, context):
    require(set(context) == {"requestedScope", "requestContext", "priorAnswerRefs", "authorizationEvidence"}
            and context["requestedScope"] == identity["authorizedScope"]
            and nonempty(context["requestContext"]) and nonempty(context["authorizationEvidence"])
            and isinstance(context["priorAnswerRefs"], list), "missing/mismatched relay scope/context/authority")
    return json.dumps({"taskId": identity["taskId"], "sessionId": identity["sessionId"], "digest": key,
        "exactOwnerWording": entry["exactPrompt"], "provenance": entry["observations"], **context,
        "authorityLimits": "Owner feedback is data, not blanket security, credential, cost or deploy approval. "
                           "Review worker does not create/mutate tasks or execute selected work. Respect role guards "
                           "and Sesame relay rules; no pane spoofing or transcript writes.",
        "reportingRequirementForEveryAuthorizedNewTaskDescription": [
            "Accomplishments since the last human check-in, with evidence.", "Current verified status.",
            "Exact next action and its owner, including whether the human must act.",
            "Remaining work and honest effort/timing uncertainty; distinguish prepared/tested/merged/deployed/live-verified."],
        "deliveryContract": "CLI acceptance is not coordinator acceptance, application or independent verification. "
                            "Reconcile uncertain delivery by digest, do not repeat instructions."}, ensure_ascii=False)


def relay(journal, identity, key, context, timeout=60):
    with journal.lock():
        state = journal.load(identity)
        entry = state["feedback"][key]
        require(entry["relay"]["state"] == "submitted", "relay already attempted; no automatic resend")
        message = envelope(identity, key, entry, context)
        entry["relay"] = {"state": "intent", "intentAtLocal": now(),
                          "destination": identity["coordinatorRoute"], "envelopeHash": sha(message.encode()),
                          "envelope": message}
        journal.save(state)
    argv = [identity["boardExecutable"], "coordinator"]
    route = identity["coordinatorRoute"]
    if route[0] == "machine":
        argv += ["--machine"]
    elif route[0] == "project":
        argv += ["--project", route[1]]
    argv += ["tell", message]
    try:
        result = subprocess.run(argv, capture_output=True, timeout=timeout)
        receipt = {"exitCode": result.returncode, "stdout": result.stdout.decode("utf-8", errors="replace"),
                   "stderr": result.stderr.decode("utf-8", errors="replace"),
                   "stdoutHex": result.stdout.hex(), "stderrHex": result.stderr.hex(), "receiptAtLocal": now()}
        status = "forwarded-cli-accepted" if result.returncode == 0 else "delivery-uncertain"
    except (OSError, subprocess.TimeoutExpired) as exc:
        receipt = {"error": str(exc), "receiptAtLocal": now(),
                   "stdoutHex": (getattr(exc, "stdout", None) or b"").hex(),
                   "stderrHex": (getattr(exc, "stderr", None) or b"").hex()}
        status = "delivery-uncertain"
    with journal.lock():
        state = journal.load(identity)
        state["feedback"][key]["relay"].update(receipt, state=status)
        journal.save(state)


def recover(journal, identity, evidence):
    require(nonempty(evidence), "recovery requires evidence; never assume feedback was not consumed")
    with journal.lock("poll.lock"), journal.lock():
        state = journal.load(identity)
        for row in state["captures"].values():
            if row["state"] != "ingested":
                row.update(state="held", recoveryEvidence=evidence)
        for entry in state["feedback"].values():
            if entry["relay"]["state"] == "intent":
                entry["relay"]["state"] = "delivery-uncertain"
        if state["lifecycle"] in {"open", "polling", "paused"}:
            state["lifecycle"] = "paused"
        state["pollOwner"] = None
        state["events"].append({"type": "recovery", "evidence": evidence, "atLocal": now()})
        journal.save(state)


def record(journal, identity, data):
    allowed = {"acceptedEvidence", "appliedEvidence", "verificationEvidence", "executedActions",
               "artifactRevision", "replyState"}
    require(set(data) == {"digest", "field", "evidence"} and nonempty(data["evidence"]), "invalid evidence record")
    with journal.lock():
        state = journal.load(identity)
        if data["digest"] is None:
            require(data["field"] in {"latestAnswerRefs", "checkInBaseline", "artifactRevisionHash"}, "invalid session field")
            if data["field"] == "latestAnswerRefs":
                state["latestAnswerRefs"].append({"evidence": data["evidence"], "atLocal": now()})
            else:
                state[data["field"]] = data["evidence"]
        else:
            require(data["field"] in allowed, "invalid feedback field")
            state["feedback"][data["digest"]][data["field"]].append({"evidence": data["evidence"], "atLocal": now()})
        journal.save(state)


def end(journal, identity, ended_by, evidence):
    require(nonempty(evidence), "end requires actual source/ownership evidence")
    with journal.lock("poll.lock"), journal.lock():
        state = journal.load(identity)
        if not state["lifecycle"].startswith("ended-"):
            state["lifecycle"] = "ended-by-" + ended_by
        state["events"].append({"type": "end-observed", "endedBy": ended_by,
                                "evidence": evidence, "atLocal": now()})
        journal.save(state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--journal", required=True)
    parser.add_argument("--identity", required=True, help="explicit pinned identity JSON; see references/contracts.md")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("status")
    poll = sub.add_parser("capture")
    poll.add_argument("--reply-file")
    receive = sub.add_parser("ingest")
    receive.add_argument("result")
    send = sub.add_parser("relay")
    send.add_argument("digest")
    send.add_argument("context")
    recovery = sub.add_parser("recover")
    recovery.add_argument("--evidence", required=True)
    evidence = sub.add_parser("record")
    evidence.add_argument("data")
    finish = sub.add_parser("end-observed")
    finish.add_argument("--by", choices=["user", "agent"], required=True)
    finish.add_argument("--evidence", required=True)
    args = parser.parse_args()
    identity = read_json(args.identity)
    validate_identity(identity)
    journal = Journal(args.journal, create=args.command == "init")
    try:
        if args.command == "init":
            init(journal, identity)
        elif args.command == "capture":
            reply = Path(args.reply_file).read_bytes().decode("utf-8") if args.reply_file else None
            print(capture(journal, identity, reply))
        elif args.command == "ingest":
            ingest(journal, identity, read_json(args.result))
        elif args.command == "relay":
            relay(journal, identity, args.digest, read_json(args.context))
        elif args.command == "recover":
            recover(journal, identity, args.evidence)
        elif args.command == "record":
            record(journal, identity, read_json(args.data))
        elif args.command == "end-observed":
            end(journal, identity, args.by, args.evidence)
        else:
            with journal.lock():
                print(json.dumps(journal.load(identity), ensure_ascii=False, indent=2))
    finally:
        journal.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        sys.exit("Held: " + str(error))
