"""Prepare/audit nonsecret instruction additions; never writes board state.

Projects 1.2.26 lacks a settings transaction/CAS API. `apply` deliberately fails.
CLI readback is opt-in because even `show` can run board housekeeping.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

KEY = "coordinator.instructions"
OPEN = "<!-- nix:herdr-projects:instructions:v1 -->"
CLOSE = "<!-- /nix:herdr-projects:instructions:v1 -->"
SUPPORTED = "1.2.26"
# Rust str::trim uses Unicode White_Space, unlike Python's broader str.strip
# (which also strips U+001C..U+001F). Match values.rs::Ty::Text exactly.
TEXT_WHITESPACE = "\t\n\v\f\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


class Refused(ValueError):
    pass


def normalized_text(text):
    """Projects 1.2.26 Ty::Text semantics, separate from raw byte ownership."""
    if text is None:
        return None
    if not isinstance(text, str):
        raise Refused("Malformed instruction text")
    trimmed = text.strip(TEXT_WHITESPACE)
    if not trimmed:
        raise Refused("Instructions need words or none; whitespace-only runtime text is invalid")
    return "none" if trimmed.lower() == "none" else trimmed


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def object_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Refused("Duplicate JSON key; ambiguous input refused")
        out[key] = value
    return out


def load(path):
    try:
        value = json.loads(Path(path).read_text(), object_pairs_hook=object_pairs)
    except (OSError, ValueError) as exc:
        raise Refused("Unreadable or malformed JSON input") from exc
    if not isinstance(value, dict):
        raise Refused("Expected JSON object")
    return value


def validate_manifest(value):
    if set(value) != {"version", "scopes"} or type(value["version"]) is not int or value["version"] != 1:
        raise Refused("Unknown declaration schema or fields")
    scopes = value["scopes"]
    if not isinstance(scopes, dict):
        raise Refused("scopes must be an object")
    for scope, settings in scopes.items():
        if scope not in ("defaults", "main", "machine") and not re.fullmatch(r"project:[A-Za-z0-9_.-]+", scope):
            raise Refused("Unknown or unsafe coordinator scope")
        if not isinstance(settings, dict) or set(settings) - {KEY}:
            raise Refused("Only coordinator.instructions is managed; other settings are refused")
        if KEY in settings:
            text = settings[KEY]
            if not isinstance(text, str) or "\x00" in text or len(text.encode()) > 48000:
                raise Refused("Instructions must be nonsecret text of at most 48000 bytes")
            if text and normalized_text(text) == "none":
                raise Refused("Use empty text to remove our block; none/reset semantics are not managed")
            if OPEN in text or CLOSE in text:
                raise Refused("Reserved management marker in declaration")
    shared = scopes.get("defaults", {}).get(KEY, "").strip(TEXT_WHITESPACE)
    if shared:
        for scope, settings in scopes.items():
            if scope != "defaults" and shared in settings.get(KEY, ""):
                raise Refused("Shared defaults must not be duplicated into scoped additions")
    return scopes


def at_scope(config, scope):
    parts = [] if scope == "defaults" else ["coordinators", scope]
    if scope.startswith("project:"):
        parts = ["coordinators", "projects", scope.removeprefix("project:")]
    at = config
    for part in parts:
        at = at.get(part, {})
        if not isinstance(at, dict):
            raise Refused("Malformed coordinator scope in runtime settings")
    return at


def own(config, scope):
    """Keep raw text for ownership/hashes; validate without discarding its bytes."""
    at = at_scope(config, scope)
    nested = at.get("coordinator", {})
    if not isinstance(nested, dict):
        raise Refused("Malformed coordinator object in runtime settings")
    if KEY in at and "instructions" in nested:
        raise Refused("Ambiguous dotted and nested instruction values")
    present = KEY in at or "instructions" in nested
    text = at.get(KEY, nested.get("instructions"))
    if present and not isinstance(text, str):
        raise Refused("Malformed runtime instructions")
    normalized_text(text)
    return text


def all_scopes(config):
    coords = config.get("coordinators", {})
    if not isinstance(coords, dict) or set(coords) - {"main", "machine", "projects"}:
        raise Refused("Malformed or unknown runtime coordinator scope")
    projects = coords.get("projects", {})
    if not isinstance(projects, dict):
        raise Refused("Malformed project coordinator entries")
    return ["defaults", "main", "machine"] + ["project:" + name for name in sorted(projects)]


def compose(old, addition, scope):
    """Pure raw preview; interpret reset tokens using the board's text semantics."""
    normalized_old = normalized_text(old)
    if addition is None:
        return old
    text = old or ""
    if text.count(OPEN) != text.count(CLOSE) or text.count(OPEN) > 1:
        raise Refused("Malformed or repeated management markers")
    if OPEN in text:
        start = text.index(OPEN)
        end = text.index(CLOSE) + len(CLOSE)
        if start >= end or (start and text[start - 1] != "\n"):
            raise Refused("Malformed management marker boundaries")
        if addition:
            return text[:start] + OPEN + "\n" + addition + "\n" + CLOSE + text[end:]
        # The two separating newlines are owned by the appended block.
        if text[max(0, start - 2):start] == "\n\n":
            start -= 2
        return (text[:start] + text[end:]) or None
    if not addition:
        return old
    if normalized_old == "none" and scope != "defaults":
        raise Refused("Scoped none suppresses broader instructions; cannot safely append")
    base = "" if normalized_old == "none" else text
    return base + ("\n\n" if base else "") + OPEN + "\n" + addition + "\n" + CLOSE


def effective(default, local=None):
    parts = []
    for raw in (default, local):
        text = normalized_text(raw)
        if text == "none":
            parts.clear()
        elif text is not None:
            parts.append(text)
    return "\n\n".join(parts) if parts else "none"


def preview(manifest, config):
    declared = validate_manifest(manifest)
    scopes = sorted(set(all_scopes(config)) | set(declared))
    before = {s: own(config, s) for s in scopes}
    after = {s: compose(before[s], declared.get(s, {}).get(KEY), s) for s in scopes}
    rows = []
    for scope in scopes:
        combined = effective(after["defaults"], None if scope == "defaults" else after[scope])
        rows.append({"scope": scope, "declared": KEY in declared.get(scope, {}),
                     "change": before[scope] != after[scope],
                     "beforeHash": digest(before[scope]), "proposedOwnHash": digest(after[scope]),
                     "proposedEffectiveHash": digest(combined)})
    return {"schema": 1, "status": "prepared-not-applied", "runtimeHash": digest(config),
            "manifestHash": digest(manifest), "scopes": rows,
            "applySupported": False, "reason": "Projects 1.2.26 has no concurrency-safe, side-effect-bounded import API"}


def cli(binary, *args):
    try:
        result = subprocess.run([binary, *args], text=True, capture_output=True,
                                stdin=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refused("Board command unavailable or timed out; no retry or fallback") from exc
    if result.returncode:
        # Never echo CLI output: it can include private instructions or task contents.
        raise Refused("Board command failed/refused; no retry or fallback")
    return result.stdout


def readback(binary, config, scopes):
    version = cli(binary, "version")
    if not re.match(r"herdr-projects " + re.escape(SUPPORTED) + r"(?:\s|$)", version):
        raise Refused("Unsupported Projects version; exact scoped contract must be revalidated")
    rows = []
    for scope in scopes:
        flags = []
        if scope == "main":
            flags = ["--main-coordinator"]
        elif scope == "machine":
            flags = ["--machine-coordinator"]
        elif scope.startswith("project:"):
            flags = ["--project-coordinator", scope.removeprefix("project:")]
        try:
            found = json.loads(cli(binary, "show", *flags, "--json"), object_pairs_hook=object_pairs)
            if found["problems"]:
                raise Refused("Board reports settings problems; readback is not verified")
            matches = [r for r in found["settings"] if r["name"] == KEY]
            if len(matches) != 1:
                raise Refused("Missing or duplicate scoped instruction readback")
            row = matches[0]
            local = own(config, scope)
            default = own(config, "defaults")
            expected = effective(default, None if scope == "defaults" else local)
            expected_place = ("you" if scope == "defaults" else "coord") if local is not None else ("you" if default is not None else "builtin")
            if (row["value"] != expected or row["place"] != expected_place
                    or row["own"] is not (local is not None) or row["note"]):
                raise Refused("Exact scoped value/provenance readback mismatch")
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, Refused):
                raise
            raise Refused("Malformed board readback") from exc
        rows.append({"scope": scope, "verified": True, "effectiveHash": digest(expected)})
    return {"schema": 1, "status": "settings-readback-verified-not-running-chat-verified",
            "version": SUPPORTED, "scopes": rows}


def settings_path():
    home = Path(os.environ.get("HERDR_PROJECTS_HOME", str(Path.home() / ".herdr-projects")))
    return Path(os.environ.get("HERDR_PROJECTS_CONFIG_DIR", str(home / "settings"))) / "config.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "readback", "apply"])
    parser.add_argument("--manifest", default=str(Path.home() / ".config/herdr-projects-nix/declarations.json"))
    parser.add_argument("--settings", default=str(settings_path()))
    parser.add_argument("--board", default=str(Path.home() / ".herdr-projects/data/bin/herdr-projects"))
    args = parser.parse_args()
    try:
        if args.command == "apply":
            if os.environ.get("HERDR_PROJECTS_ID"):
                raise Refused("Task-tagged caller cannot change coordinator settings; context is preserved")
            raise Refused("No safe import API in Projects 1.2.26: apply disabled; no board command executed")
        path = Path(args.settings)
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise Refused("Settings must be an existing regular file, never a managed/store symlink")
        config = load(path)
        manifest = load(args.manifest)
        prepared = preview(manifest, config)
        if args.command == "plan":
            out = prepared
        else:
            out = readback(args.board, config, [r["scope"] for r in prepared["scopes"]])
            if load(path) != config:
                raise Refused("Settings changed during readback; result is unverified")
        print(json.dumps(out, sort_keys=True, indent=2))
        return 0
    except (Refused, OSError) as exc:
        print("Refused: " + (str(exc) if isinstance(exc, Refused) else "Settings unavailable"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
