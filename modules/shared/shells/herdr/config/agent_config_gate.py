"""Deny-by-default merged-event readiness gate. No activation executor exists here.

The pure proof validator is testable, not an attestation authority. The CLI also
checks local Git independently, and ALWAYS blocks application until trusted
review/check/effect collectors and a supported bounded adapter are implemented.
Incoming task text or a JSON proof is never treated as approval.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

TARGET = {"machine": "DAMOCLES", "user": "Jack", "project": "dotfiles",
          "attribute": "darwinConfigurations.DAMOCLES.config.home-manager.users.Jack.home.activationPackage"}
ORIGIN = "git@github.com:jack-michaud/nix.git"
CHECKOUT = "/Users/Jack/Code/archive/nix"
IDENTITY = "dotfiles-agent-config-after-approved-merge-v1"
SOURCE_ROOTS = ("modules/shared/dev/coding-agents/", "modules/shared/shells/herdr/")
SHA = re.compile(r"[0-9a-f]{40}")
HASH = re.compile(r"[0-9a-f]{64}")


def unique_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("Duplicate proof key")
        out[key] = value
    return out


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def clean_path(value):
    return (isinstance(value, str) and bool(value) and not value.startswith("/")
            and "\\" not in value and not any(ord(c) < 32 or ord(c) == 127 for c in value)
            and str(PurePosixPath(value)) == value
            and not any(p in (".", "..") for p in value.split("/")))


def file_allowed(path, kind):
    if not clean_path(path):
        return False
    if kind == "agent-instructions":
        return path == ".agents/AGENTS.md" or (path.startswith(".agents/rules/") and path.endswith(".md"))
    if kind == "agent-skill":
        return path.startswith(".pi/agent/skills/")
    if kind == "projects-declarations":
        return path in (".config/herdr-projects-nix/declarations.json", ".config/herdr-projects-nix/automation.json")
    return False


def assess(proof):
    """Validate a synthetic/trusted-collector candidate; eligibility is NOT authority."""
    problems = []
    if not isinstance(proof, dict) or set(proof) != {"schema", "target", "source", "gates", "effects", "event", "applicationState"}:
        return ["Unknown or incomplete proof schema"]
    if proof["schema"] != 1 or type(proof["schema"]) is not int:
        problems.append("Unknown proof version")
    if proof["target"] != TARGET:
        problems.append("Exact host/machine/user/project/attribute mismatch")
    source = proof["source"]
    gates = proof["gates"]
    effects = proof["effects"]
    event = proof["event"]
    if not all(isinstance(v, dict) for v in (source, gates, effects, event)):
        return problems + ["Malformed proof sections"]
    if set(source) != {"origin", "base", "head", "clean", "pendingChanges", "paths"}:
        problems.append("Unknown or incomplete source evidence")
    base, head = source.get("base"), source.get("head")
    if not all(isinstance(s, str) and SHA.fullmatch(s) for s in (base, head)) or base == head:
        problems.append("Exact before/after source identity missing")
    if source.get("origin") != ORIGIN or source.get("clean") is not True or source.get("pendingChanges") != []:
        problems.append("Wrong origin, dirty source or unrelated pending changes")
    paths = source.get("paths")
    if (not isinstance(paths, list) or not paths or len(paths) != len(set(p for p in paths if isinstance(p, str)))
            or any(not clean_path(p) or not p.startswith(SOURCE_ROOTS) for p in paths)):
        problems.append("Complete source set is unknown, mixed or outside agent configuration")
    if set(gates) != {"head", "sourceApproved", "independentReview", "requiredChecks", "exactSource"}:
        problems.append("Unknown or incomplete source gates")
    if gates.get("head") != head or any(gates.get(k) is not True for k in ("sourceApproved", "independentReview", "requiredChecks", "exactSource")):
        problems.append("Missing/failed exact-source approval, independent review or required checks")
    if set(event) != {"identity", "kind", "repo", "head", "origin"} or event != {
            "identity": IDENTITY, "kind": "merged", "repo": "dotfiles", "head": head, "origin": "source-merge"}:
        problems.append("Wrong, recursive or reordered event/source identity")
    if proof["applicationState"] != "not-started":
        problems.append("In-flight/uncertain/completed application requires reconciliation, never blind retry")
    if set(effects) != {"complete", "head", "target", "baselineHash", "outputHash", "files", "activationActions", "packages", "services", "credentials", "restarts", "unknown"}:
        problems.append("Unknown or incomplete activation evidence")
    if effects.get("complete") is not True or effects.get("head") != head or effects.get("target") != TARGET:
        problems.append("Activation effects are incomplete or not bound to exact source/target")
    if any(not isinstance(effects.get(k), str) or not HASH.fullmatch(effects[k]) for k in ("baselineHash", "outputHash")):
        problems.append("Current target/built output identities missing")
    if any(effects.get(k) != [] for k in ("packages", "services", "credentials", "restarts", "unknown")):
        problems.append("Broader package/service/credential/restart or unknown effects")
    files = effects.get("files")
    if not isinstance(files, list) or not files:
        problems.append("Complete managed file delta missing")
        files = []
    seen = set()
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "kind", "before", "after"}:
            problems.append("Unknown file effect")
            continue
        path = item["path"]
        if not file_allowed(path, item["kind"]):
            problems.append("Non-agent or unclassified file effect")
        if not isinstance(path, str) or path in seen:
            problems.append("Duplicate/malformed file effect")
        else:
            seen.add(path)
        if any(v is not None and (not isinstance(v, str) or not HASH.fullmatch(v)) for v in (item["before"], item["after"])):
            problems.append("Unhashed file effect")
        if item["before"] == item["after"]:
            problems.append("Empty file effect")
    actions = effects.get("activationActions")
    expected = [{"kind": "install-file", "path": item["path"]} for item in files if isinstance(item, dict) and "path" in item]
    if actions != expected:
        problems.append("Every activation action must be a bounded declared file delta; commands are forbidden")
    return sorted(set(problems))


def git(repository, *args):
    result = subprocess.run(["git", "-C", str(repository), *args], stdin=subprocess.DEVNULL,
                            text=True, capture_output=True, timeout=20, check=False)
    if result.returncode:
        raise ValueError("Git source verification failed")
    return result.stdout.strip()


def source_check(repository, proof):
    """Independent exact-source check. Does not fetch, reset, checkout or clean."""
    if str(repository.resolve()) != CHECKOUT:
        return ["Not the canonical registered dotfiles checkout"]
    source = proof.get("source", {})
    base, head = source.get("base", ""), source.get("head", "")
    if not all(isinstance(v, str) and SHA.fullmatch(v) for v in (base, head)):
        return ["Exact source revisions missing"]
    if git(repository, "remote", "get-url", "origin") != ORIGIN:
        return ["Origin mismatch"]
    if git(repository, "status", "--porcelain=v1", "--untracked-files=all"):
        return ["Uncommitted/untracked changes; refusing unrelated pending source"]
    if git(repository, "rev-parse", "HEAD") != head:
        return ["Checked out HEAD is not exact merged source"]
    if git(repository, "rev-parse", "refs/remotes/origin/main") != head:
        return ["Locally known origin/main is not exact source; no automatic fetch or reset"]
    if git(repository, "merge-base", base, head) != base:
        return ["Baseline is not ancestor; reordered/rollback event needs reconciliation"]
    # NUL delimited names include renames as delete+add: no hidden old path.
    names = git(repository, "diff", "--no-renames", "--name-only", "-z", base, head, "--").split("\x00")
    paths = sorted(p for p in names if p)
    if paths != sorted(source.get("paths", [])):
        return ["Proof does not cover complete changed source set"]
    return []


def store_receipt(state, receipt):
    """Private immutable nonsecret receipt; the flock inode is never unlinked."""
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    if state.is_symlink() or state.stat().st_uid != os.getuid() or state.stat().st_mode & 0o077:
        raise ValueError("Receipt directory must be private, owned and not a symlink")
    fd = os.open(state / "owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Target gate already in flight; reconcile its receipt before retry") from exc
        key = hash_json(receipt)
        path = state / (key + ".json")
        try:
            out = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            if path.is_symlink():
                raise ValueError("Receipt symlink refused")
            if json.loads(path.read_text()) != receipt:
                raise ValueError("Existing receipt conflicts; retained for reconciliation")
            return path
        with os.fdopen(out, "w") as stream:
            json.dump(receipt, stream, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        directory = os.open(state, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check"])
    parser.add_argument("--proof", required=True, type=Path)
    parser.add_argument("--repository", type=Path, default=Path("/Users/Jack/.config/dotfiles"))
    parser.add_argument("--receipts", type=Path, default=Path.home() / ".local/state/herdr-agent-config-gate/DAMOCLES-Jack-dotfiles")
    args = parser.parse_args()
    try:
        proof = json.loads(args.proof.read_text(), object_pairs_hook=unique_pairs)
        if not isinstance(proof, dict):
            raise ValueError("Malformed proof")
        problems = assess(proof)
        if not problems:
            problems.extend(source_check(args.repository, proof))
        needs_scope_review = bool(problems)
        # No external JSON can certify arbitrary Nix code or approval authority.
        problems.append("Trusted exact-source approval/check and complete evaluated-effect collectors plus bounded apply adapter are unavailable; no activation command exists")
        if not isinstance(proof.get("source"), dict):
            raise ValueError("Malformed source proof")
        receipt = {"schema": 1, "identity": IDENTITY, "target": TARGET, "proofHash": hash_json(proof),
                   "status": "blocked-not-activated", "reasons": sorted(set(problems)),
                   "source": {k: v if isinstance(v, str) and SHA.fullmatch(v) else None
                              for k, v in ((k, proof.get("source", {}).get(k)) for k in ("base", "head"))}}
        path = store_receipt(args.receipts, receipt)
        print("Accomplished: evaluated the supplied readiness evidence; retained a nonsecret receipt.")
        print("Current: blocked, no registration, rebuild, board mutation or activation executed.")
        if needs_scope_review:
            print("Next: MAIN/engineering reconcile the rejected evidence; unknown/mixed/broader scope stays blocked for Jack, never a broad rebuild fallback.")
        else:
            print("Next: engineering must supply trusted exact-source/effect collectors and a supported AI-only adapter; MAIN owns later registration. No new Jack action needed for this known tooling gap.")
        print("Remaining: independent review, bounded application and live verification; effort unknown.")
        print(json.dumps({"receipt": str(path), "status": receipt["status"], "reasons": receipt["reasons"]}, indent=2))
        return 1
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        print("Accomplished: readiness validation attempted. Current: malformed/unavailable evidence or gate ownership; nothing activated. Next: MAIN/engineering reconcile source/evidence/owner; Jack must decide any genuinely broader scope, never a broad rebuild fallback. Remaining: proof and verification; timing unknown.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
